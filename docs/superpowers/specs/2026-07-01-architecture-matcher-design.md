# ArchitectureMatcher — Design Spec

## Problem

The enforcer has `ImportMatcher` — it flags import statements matching
forbidden regex patterns. That covers point rules like "matchers must not
import from runner/cli" (the repo's own `matchers-no-import-runner-cli`
rule). But it cannot express **layer dependency rules**, the core of
architectural enforcement:

> "Files in layer A may not import from layer B."
> "Services may import repositories, but repositories may not import services."
> "Domain code may not import from the framework layer."

This is the archunit-shaped hole. Today a user would have to write one
`ImportMatcher` per forbidden source-directory, with a regex enumerating
every target path. Fragile, verbose, and no graph awareness — it can't
follow transitive imports, so a violation hidden behind one hop ships
undetected.

## Goal

A first-class `ArchitectureMatcher` that:

1. Declares layers as glob → layer-name mappings.
2. Declares allowed edges as `(source_layer, target_layer)` pairs.
3. Flags imports where `(source_layer, target_layer)` is not in
   `allowed_edges` (when `forbid_implicit=True`) or is in an explicit
   `forbidden_edges` list (when `forbid_implicit=False`).
4. Builds an import graph from staged files + transitive closure, so
   newly-reachable violations across the staged boundary are caught.
5. Composes with the existing matcher/predicate/combinator/Rule
   infrastructure — no special-case runner path.

Deterministic: no LLM. Built once per run from file contents.

## Non-Goals (YAGNI)

- **Cycle detection.** Layer-dependency matrix covers the common case.
  Add cycle detection when a user asks.
- **Declarative YAML/TOML rule form.** The `Rule(matchers=[...])` +
  matcher dataclass model already covers rule authoring. A decorator DSL
  was considered and rejected as duplication — two syntaxes for the same
  thing.
- **External layer config file.** Layers declared as dataclass fields on
  the matcher. One file, one source of truth.
- **End-user test enforcement.** The repo's `core-test-paired` /
  `matcher-test-positive-negative` rules are self-enforcement for this
  repo only. End-users do not inherit them. The new matcher ships with
  paired tests in this repo because it lives here.

## Design

### `ImportGraphBuilder` (`enforcer/import_graph.py`)

Builds a directed import graph: `{source_path: set[target_path]}`.

**Input:** staged file list, workspace path, `FileContextBuilder` (for
parse-once caching).

**Algorithm:**

1. Seed: staged files (Python only for v1 — `ArchitectureMatcher` is
   `AST_PY`. TS support added when a TS-using repo asks).
2. For each seed file, parse imports via tree-sitter (`Needs.AST_PY`).
   Reuse `IMPORT_NODE_TYPES` from `parsers/ast_utils.py`.
3. Resolve each import to an on-disk path:
   - `import foo.bar` → `foo/bar/__init__.py` or `foo/bar.py` or `foo.py`
   - `from foo.bar import X` → same resolution
   - Relative imports (`from . import x`, `from ..foo import y`) resolved
     against the importing file's package.
4. For each resolved target that exists on disk and is not already in
   the graph, recurse: parse its imports, add edges. Continue until
   closure (no new nodes).
5. Skip: stdlib, third-party (unresolvable → not a violation target),
  non-`.py` files.

**Output:** `dict[str, set[str]]` stored in
`shared_ctx["__import_graph__"]`.

**Where invoked:** `check_runner.build_shared_ctx()` — only if any rule
contains an `ArchitectureMatcher` (cheap detection: walk matcher trees
once, check for `hasattr(m, "layers")`). This keeps zero-cost for configs
that don't use architecture rules.

**Bounded:** transitive closure can be large. Cap at `max_files`
(default 500). If exceeded, log a warning to stderr and stop expanding
(union closure reached; staged files themselves still fully checked).
Mark this as a known ceiling in a `ponytail:` comment.

### `ArchitectureMatcher` (`enforcer/matchers/architecture.py`)

```python
@dataclass
class ArchitectureMatcher:
    """Flags imports crossing forbidden layer boundaries.

    What:       flags import statements where (source_layer, target_layer)
                is not in allowed_edges (forbid_implicit=True) or is in
                forbidden_edges (forbid_implicit=False)
    Ignores:    imports to unresolvable targets (stdlib, third-party);
                intra-layer imports; files not matching any layer glob
    Basis:      AST_PY
    shared_ctx: reads __import_graph__ (dict[str, set[str]]) built by
                ImportGraphBuilder; reads __workspace__
    """
    layers: dict[str, list[str]]               # layer name -> globs
    allowed_edges: list[tuple[str, str]] = field(default_factory=list)
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    forbid_implicit: bool = True               # edges not in allowed = violation
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        # ponytail: precompute layer-name lookup: glob-pattern -> layer
        # _layer_for_path uses _glob_match from enforcer.rule
        ...

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        graph = (shared_ctx or {}).get("__import_graph__", {})
        targets = graph.get(file_ctx.path, set())
        src_layer = self._layer_for_path(file_ctx.path)
        if src_layer is None:
            return []  # file not in any declared layer
        matches = []
        for tgt in targets:
            tgt_layer = self._layer_for_path(tgt)
            if tgt_layer is None:
                continue  # unresolvable or not in a layer — not our concern
            if tgt_layer == src_layer:
                continue  # intra-layer, always allowed
            edge = (src_layer, tgt_layer)
            if self._is_forbidden(edge):
                matches.append(Match(
                    file=file_ctx.path,
                    line=self._import_line_for(file_ctx, tgt),
                    matched_value=f"{src_layer} -> {tgt_layer}",
                ))
        return matches

    def _is_forbidden(self, edge: tuple[str, str]) -> bool:
        if self.forbid_implicit:
            return edge not in self.allowed_edges
        return edge in self.forbidden_edges

    def _layer_for_path(self, path: str) -> str | None:
        # iterate layers, return first whose globs match via _glob_match
        ...

    def _import_line_for(self, file_ctx: FileContext, target: str) -> int:
        # walk file_ctx.ast for import nodes, find the one resolving to target
        # return its start_line; fallback 0 if not found
        ...
```

**Design notes:**

- **Two-phase? No.** The graph is built in `build_shared_ctx` (pre-rule
  phase) and stored in `shared_ctx`. `find()` is per-file and reads the
  pre-built graph. No `finalize_duplicates` needed — each violation is
  local to its importing file.
- **`diff_only`:** left to the `Rule`, not the matcher. An
  `ArchitectureMatcher` rule can set `diff_only=True` (only check
  imports on changed lines) or `diff_only=False` (check all imports in
  staged files). Default recommendation: `diff_only=False` — a newly
  staged file's *existing* imports matter as much as new ones.
- **Line attribution:** `Match.line` points at the import statement in
  the source file. `_import_line_for` walks `file_ctx.ast` (already
  populated because `needs=AST_PY`) and matches the import node to the
  target path. Fallback `line=0` if resolution fails (file-level match,
  still useful).
- **No combinator special-casing.** `ArchitectureMatcher` is a plain
  matcher — composes with `AllOf`, `AnyOf`, `Not`, predicates. E.g.
  `AllOf(ArchitectureMatcher(...), Not(RegexMatcher(r"# allow-break")))`
  would let a `# allow-break` comment suppress the violation.
- **Glob matching** reuses `enforcer.rule._glob_match` (already
  `**`-aware). No new glob logic.

### Integration with `check_runner.build_shared_ctx`

```python
def build_shared_ctx(config, builder, ws: str) -> dict:
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    # ... existing read_targets logic ...

    if _has_architecture_matcher(config.rules):
        from enforcer.import_graph import ImportGraphBuilder
        graph_builder = ImportGraphBuilder(builder=builder, workspace=ws)
        shared_ctx["__import_graph__"] = graph_builder.build(staged_files)

    return shared_ctx
```

`build_shared_ctx` gains an optional `staged_files: list[str] = None`
parameter (default `None`). `cli.py` and `mcp_server.py` already have
the file list (from `collect_files`) before calling `build_shared_ctx`
— they pass it through as `staged_files=file_list`. One-line change at
each call site. No broader signature churn.

**Detection:** `_has_architecture_matcher(rules)` walks each rule's
matcher tree (reuse `_collect_needs` pattern from `context.py`) and
returns `True` if any matcher has a `layers` attribute. Cheap, runs once.

### Config example (self-enforcement)

Add to `enforcer_config.py`:

```python
Rule(
    id="arch-layer-deps",
    severity=Severity.ERROR,
    matchers=[ArchitectureMatcher(
        layers={
            "types":     ["enforcer/types.py"],
            "rule":      ["enforcer/rule.py"],
            "core":      ["enforcer/runner.py", "enforcer/context.py",
                          "enforcer/config.py", "enforcer/check_runner.py"],
            "matchers":  ["enforcer/matchers/**/*.py"],
            "predicates":["enforcer/predicates/**/*.py"],
            "combinators":["enforcer/combinators/**/*.py"],
            "extractors":["enforcer/extractors/**/*.py"],
            "parsers":   ["enforcer/parsers/**/*.py"],
            "io":        ["enforcer/cli.py", "enforcer/mcp_server.py",
                          "enforcer/reporter.py", "enforcer/docs.py",
                          "enforcer/explain.py", "enforcer/fix.py",
                          "enforcer/ignore.py", "enforcer/llm.py"],
        },
        allowed_edges=[
            ("matchers", "types"),
            ("matchers", "parsers"),
            ("predicates", "types"),
            ("combinators", "types"),
            ("combinators", "matchers"),
            ("extractors", "types"),
            ("core", "types"),
            ("core", "rule"),
            ("core", "parsers"),
            ("core", "matchers"),
            ("core", "combinators"),
            ("core", "extractors"),
            ("io", "types"),
            ("io", "rule"),
            ("io", "core"),
            ("io", "parsers"),
            ("io", "matchers"),
            ("io", "combinators"),
            ("io", "extractors"),
            ("parsers", "types"),
        ],
        forbid_implicit=True,
    )],
    file_globs=["enforcer/**/*.py"],
    exclude_globs=["enforcer/__init__.py"],
    diff_only=False,
    message="Layer violation: {matched_value} at {file}:{line}",
    fix_instruction="Move shared logic down to a lower layer, or add the edge to allowed_edges if intentional.",
    rationale="Importing upward creates circular deps and prevents isolated testing. Layers: types < rule/parsers/matchers/predicates/combinators/extractors < core < io.",
)
```

This subsumes the three existing `ImportMatcher`-based layer rules
(`matchers-no-import-runner-cli`, `rule-no-import-up`,
`runner-no-import-cli`) as special cases. Those rules stay (they're
fast, no graph needed, and good documentation), but the
`ArchitectureMatcher` rule is the comprehensive backstop.

### Testing

Per repo convention: paired test file, positive + negative parameterized
(>=3 cases each).

**`tests/test_matchers/test_architecture.py`**

Positive (`test_architecture_flags`):
- matchers file importing from cli → flagged
- core file importing from cli → flagged
- io file importing from matchers (not in allowed_edges) → flagged
- file in undeclared layer importing a declared layer → not flagged
  (negative control, ensures unknown-source-layer is allowed)

Negative (`test_architecture_clean`):
- matchers file importing from types → clean
- intra-layer import → clean
- file importing stdlib/third-party (unresolvable) → clean
- file not matching any layer glob → clean

**`tests/test_import_graph.py`**

- Two-file graph: a.py imports b.py → `{a: {b}}`
- Transitive: a imports b, b imports c → `{a: {b}, b: {c}}`
- Closure stops at unresolvable (stdlib) → not in graph
- Relative import resolution: `from . import sibling` → resolves to
  sibling.py in same package
- `max_files` cap: synthetic 600-file graph → stops at 500, stderr
  warning, staged files still fully checked

**Shared context fixture:** tests inject a pre-built
`shared_ctx["__import_graph__"]` dict so `ArchitectureMatcher.find()`
can be tested in isolation without the graph builder.

## Files

New:
- `enforcer/import_graph.py` — `ImportGraphBuilder`
- `enforcer/matchers/architecture.py` — `ArchitectureMatcher`
- `tests/test_matchers/test_architecture.py`
- `tests/test_import_graph.py`

Modified:
- `enforcer/matchers/__init__.py` — export `ArchitectureMatcher`
- `enforcer/check_runner.py` — `build_shared_ctx` gains
  `staged_files` param + conditional graph build

No changes to: `types.py`, `rule.py`, `runner.py`, `context.py`,
`config.py`, `reporter.py`, `fix.py`, `cli.py` (beyond passing
`staged_files` through — one line), `mcp_server.py` (same).

## Migration / Backward Compatibility

Fully additive. No existing API changes. Configs without
`ArchitectureMatcher` pay zero cost (graph build is gated on detection).
The three existing `ImportMatcher` layer rules remain valid and
unaffected — they're a subset of what `ArchitectureMatcher` expresses,
but they're faster (no graph) and serve as documentation.

## Open Questions

None. All resolved during brainstorm:
- Graph scope: staged + transitive closure (confirmed)
- Layer declaration: matcher dataclass fields (confirmed)
- Cycle detection: YAGNI, skip (confirmed)
- Decorator DSL: rejected as duplication (confirmed)

## Follow-On: Facade & Interface Pattern Rules

### Problem

`ArchitectureMatcher` enforces layer *edges* (who may import whom). It
cannot enforce *module shape*: "every service submodule exposes a
facade," "every facade re-exports an interface," "every facade has a
single public entry point." These are structural pattern rules —
deterministic, composable, hard gates.

Three rules cover the facade pattern:

1. **Facade exists** — every submodule matching a glob has a facade
   file (`__init__.py` / `index.ts`). Existence check.
2. **Facade exposes interface** — the facade file re-exports or declares
   a `Protocol` / `ABC` / TS `interface`. AST shape check.
3. **Internals not imported externally** — files outside the submodule
   import the facade, not internals. Already expressible with
   `ArchitectureMatcher` (layer = `*_facade` vs `*_internal`).

Rules 1 and 3 are feasible with existing + proposed matchers. Rule 2
needs one new small matcher.

### Rule 1: Facade exists

Use `FileExistsMatcher` (already in `enforcer/matchers/file_exists.py`)
or `PairedFileMatcher` variant. Declared per-submodule via glob:

```python
Rule(
    id="service-facade-exists",
    severity=Severity.ERROR,
    matchers=[FileExistsMatcher(required_path="index.ts")],
    file_globs=["src/services/*/"],
    message="Service dir {file} has no facade (index.ts)",
    fix_instruction="Create src/services/{file}/index.ts re-exporting the public API.",
)
```

**Feasibility:** today. `FileExistsMatcher` checks for a required path
relative to the matched file's directory. If its current contract is
file-level not dir-level, a thin `FacadeExistsMatcher` wraps it — ~20
lines, same `find()` contract.

**Gap to verify:** does `FileExistsMatcher` accept directory globs and
resolve `required_path` relative to the directory? If not, add
`FacadeExistsMatcher(source_glob="src/services/*", facade="index.ts")`
that lists directories matching `source_glob` and flags those missing
`{dir}/{facade}`. Reuses `_glob_match`. No AST.

### Rule 2: Facade exposes interface (NEW)

`FacadeExposesInterfaceMatcher` — small AST matcher, ~50 lines.

```python
@dataclass
class FacadeExposesInterfaceMatcher:
    """Flags facade files that don't expose a public interface
    (Protocol/ABC in Python, interface in TS).

    What:       flags facade files with no interface-type declaration
                or re-export in their top-level statements
    Ignores:    non-facade files (gated by Rule.file_globs); private
                (_-prefixed) symbols
    Basis:      AST_PY (default; AST_TS when overridden)
    shared_ctx: none
    """
    interface_bases: tuple[str, ...] = ("Protocol", "ABC")
    ts_interface_keyword: str = "interface"
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx, shared_ctx=None):
        if not file_ctx.ast:
            return []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if self._is_interface_decl(node):
                return []  # found one — clean
        return [Match(file=file_ctx.path, line=1,
                      matched_value="no interface exposed")]
```

**Python detection:** `class_definition` node whose bases include
`Protocol` or `ABC` (from `typing` / `abc`). Walk bases, match name.
Also accept `__all__` entries pointing at such classes (re-export).

**TS detection:** `interface_declaration` node, or `export` statement
re-exporting an interface. Tree-sitter node types already in
`IMPORT_NODE_TYPES`-adjacent constants.

**Composition:** pair with `ArchitectureMatcher` via `AllOf`:
"facade exists AND exposes interface AND no external internal-imports."
Or as separate rules — cleaner, each rule has its own message + fix
instruction.

### Rule 3: Internals not imported externally

Pure `ArchitectureMatcher` config — no new code:

```python
ArchitectureMatcher(
    layers={
        "service_facade":   ["src/services/*/index.ts"],
        "service_internal": ["src/services/*/!(index).ts"],
        "external":         ["src/**"],  # broad, refined via exclude_globs
    },
    forbidden_edges=[("external", "service_internal")],
    forbid_implicit=False,
)
```

Consumers importing `service_internal/*` directly → flagged. Must import
via `service_facade`. This is the facade pattern's enforcement edge.

### Composed rule (full facade pattern)

Three separate `Rule` entries, each focused:

```python
Rule(id="facade-exists", matchers=[FacadeExistsMatcher(...)], ...)
Rule(id="facade-exposes-interface", matchers=[FacadeExposesInterfaceMatcher(...)], ...)
Rule(id="facade-no-internal-import", matchers=[ArchitectureMatcher(...)], ...)
```

Separate rules over one `AllOf` rule — each has a distinct message and
fix instruction, and partial compliance is visible (rule 1 passes
while rule 2 fails tells the user exactly what's missing).

### Testing

Per repo convention: paired tests, positive + negative parameterized
(>=3 cases each).

**`tests/test_matchers/test_facade_exists.py`**
- Positive: dir with no `index.ts` → flagged; dir with no `__init__.py` → flagged
- Negative: dir with facade → clean; non-matching dir → clean

**`tests/test_matchers/test_facade_exposes_interface.py`**
- Positive: facade with only impl classes → flagged; facade with no
  classes → flagged; TS facade with no `interface` → flagged
- Negative: facade with `class X(Protocol)` → clean; facade re-exporting
  a Protocol via `__all__` → clean; TS facade with `interface X {}` → clean

### Files (follow-on)

New:
- `enforcer/matchers/facade_exists.py` — `FacadeExistsMatcher` (if
  `FileExistsMatcher` doesn't cover dir-level)
- `enforcer/matchers/facade_exposes_interface.py` — `FacadeExposesInterfaceMatcher`
- `tests/test_matchers/test_facade_exists.py`
- `tests/test_matchers/test_facade_exposes_interface.py`

Modified:
- `enforcer/matchers/__init__.py` — export new matchers

No core changes. These are plain matchers — no `shared_ctx` graph
needed (rule 3 reuses `__import_graph__` from `ImportGraphBuilder`).

### Feasibility verdict

- Rule 1 (facade exists): feasible today or with ~20-line wrapper.
- Rule 2 (exposes interface): feasible, ~50 lines, one new matcher.
- Rule 3 (no internal import): feasible with `ArchitectureMatcher` as
  designed in this spec.

All deterministic, all compose with existing Rule/combinator
infrastructure. No LLM, no new core types.

### Open question (follow-on)

- `FileExistsMatcher` dir-level support: verify contract before deciding
  whether `FacadeExistsMatcher` is a wrapper or a standalone matcher.
  Resolved at implementation time — read `file_exists.py`, decide.

## Sequence

### Phase 1: Architecture matcher (this spec's core)

1. `ImportGraphBuilder` + tests
2. `ArchitectureMatcher` + tests
3. Wire into `check_runner.build_shared_ctx`
4. Add `arch-layer-deps` rule to `enforcer_config.py`
5. `enforcer check --staged` on this repo — must pass
6. `pytest` — all green

### Phase 2: Facade pattern rules (follow-on)

7. Verify `FileExistsMatcher` dir-level support; add `FacadeExistsMatcher`
   if needed + tests
8. `FacadeExposesInterfaceMatcher` + tests
9. Add facade pattern rules to `enforcer_config.py` (self-enforcement
   for `enforcer/` submodules)
10. `pytest` — all green
