# Ontology Graph — Design Spec

## Problem

Repositories degrade in three stages, each invisible at the commit level:

1. **Drift** — a type gets renamed in code; docs still use the old name. A new
   concept (`Extractor`) appears in code but is never declared anywhere, so the
   next agent session doesn't know it exists or what to call it. Ontology and
   code desync silently.
2. **Boundary rot** — a module that was clearly "core types" starts importing
   CLI concerns. A matcher grows a hidden dependency on another file via
   `shared_ctx`. The layer graph on paper says X, code does Y. Boundaries blur
   over months.
3. **No canonical index** — agents can't answer "what is X and where does it
   live?" without grep-and-guess. No single place lists every concept, its
   canonical name, its location, its role, its relationships. Each agent
   re-derives the ontology every session, slightly differently.

Root cause: docs are hand-maintained, code is scattered, and nothing blocks
the gap between them from widening.

## Goal

A code-as-ontology layer: the code's public symbols ARE the ontology, a
generated graph is the LLM-readable projection, and enforcer rules keep code
and graph in sync. Specifically:

1. A `ConceptGraphBuilder` that walks the repo's AST + import graph and emits
   a structured `ConceptGraph` (symbols, kinds, locations, layers, `What:`
   docstrings, dependency edges).
2. A render pipeline that writes `ONTOLOGY.md` (markdown) and optionally JSON.
3. CLI commands `enforcer graph` and `enforcer sync-graph`, mirroring
   `docs` / `sync-doc`.
4. Six self-enforcement rules (one per failure mode family, see below) wired
   into `enforcer_config.py` so drift, rot, and missing index all block
   commits.

Generic shape — the abstractions work for any Python repo. First slice
implemented and validated on this repo only.

## Non-Goals (YAGNI)

- **TypeScript/JS concept extraction.** `ImportGraphBuilder` is Python-only
  today; concept extraction follows. Add TS when a TS repo adopts this.
- **Relative import resolution.** Already deferred in `ImportGraphBuilder`.
  Reuse that deferral.
- **Concept rename detection across commits.** Needs git-history diffing.
  Add when a user reports a real "renamed symbol slipped through" case.
- **`CONCEPTS.yaml` overlay (approach B).** A hand-maintained registry is the
  disease we're curing. Add only if "should this concept exist?" (vs. "is this
  concept well-formed?") becomes a real question.
- **Live query API / LSP server.** The graph is a rebuilt artifact. Agents
  read `ONTOLOGY.md`. No long-running process.
- **Cycle detection on the concept graph.** Layer-boundary rules cover the
  common rot case. Add cycle detection when a user asks.

## Design

### Data Model (`enforcer/concept_graph.py`)

```python
@dataclass
class Concept:
    name: str          # canonical: "enforcer.rule.Rule"
    kind: str          # "class" | "function" | "dataclass"
    file: str          # relative path
    line: int
    layer: str         # computed from layer globs
    what: str          # extracted from docstring "What:" section
    imports: set[str]  # canonical names this concept depends on (best-effort)
    public: bool       # in __all__ or no leading underscore

@dataclass
class ConceptGraph:
    symbols: dict[str, Concept]       # keyed by canonical name
    imports: dict[str, set[str]]      # path -> set[path] (from ImportGraphBuilder)
    layers: dict[str, str]            # path -> layer name
```

### Builder Pipeline (`ConceptGraphBuilder`)

Mirrors `ImportGraphBuilder.build`. Same constructor shape
(`builder: FileContextBuilder, workspace: str, max_files: int = 500`).

1. Reuse `ImportGraphBuilder` for the path-level import graph. Do not
   duplicate AST walking for imports.
2. For each `.py` file reachable from the staged set + transitive closure:
   - Parse via `FileContextBuilder` (parse-once cache).
   - Walk AST iteratively (DFS, never recursive — precedent
     `import_matcher.py:55`).
   - Collect `class_definition` and `function_definition` nodes → `Concept`
     records.
   - Determine `kind`: `dataclass` if `@dataclass` decorator present (mirror
     `interface_check.py:52`), else `class` / `function`.
   - Determine `public`: symbol name has no leading `_`, OR appears in the
     file's `__all__`.
   - Extract `what` from docstring: first `expression_statement` /
     `module` docstring / `block` string, regex `^What:\s*(.+)$` (multiline).
     Empty string if absent — the docstring rule (1.2) catches that.
3. Stamp `layer` per file via configurable `layers: dict[str, list[str]]`
   (same shape as `ArchitectureMatcher.layers`). First matching glob wins.
4. Resolve `imports` to canonical names: for each path in
   `ImportGraphBuilder`'s output, map to the concept(s) defined in that file.
   Best-effort — unresolved targets silently dropped.
5. Stash the set of public symbol canonical names into
   `shared_ctx["__public_symbols__"]` during `build()`. Rule 3.2 reads this
   set; rule 3.2's own `find()` is a no-op that exists only so the finalizer
   gets registered.

**`__all__` detection:** walk the module-level nodes for an
`assignment` whose left-hand side is `__all__`. The right-hand side is a
`list`/`tuple` of `string` literals — extract those strings. A symbol is
`public` if it has no leading `_` OR appears in this extracted set.

### Renderers (`enforcer/concept_graph.py`)

Two functions, parallel to `render_rules_doc` / `render_rules_markdown`:

- `render_ontology_markdown(graph: ConceptGraph) -> str` — human/LLM-readable.
- `render_ontology_json(graph: ConceptGraph) -> str` — structured form.

**Markdown format** (deterministic, diff-friendly — everything sorted):

```markdown
# Ontology

_Auto-generated by `enforcer sync-graph`. Do not edit by hand._
_N symbols, M relationships. Source of truth: the code._

## Layers

- `types` — `enforcer/types.py`
- `core` — `enforcer/rule.py`, `enforcer/runner.py`, ...
- `matchers` — `enforcer/matchers/**`

## Concepts

### `enforcer.types.Match`
- kind: dataclass
- file: enforcer/types.py:41
- layer: types
- what: A single rule violation found in a file.

### `enforcer.rule.Rule`
- kind: dataclass
- file: enforcer/rule.py
- layer: core
- what: composes matchers + predicates + message into a checkable unit
- depends on: enforcer.types.Match, enforcer.types.Severity, ...

## Imports (edges)

- enforcer/rule.py -> enforcer/types.py
- enforcer/matchers/architecture.py -> enforcer/types.py
- enforcer/matchers/architecture.py -> enforcer/parsers/ast_utils.py
```

Sections sorted by name; bullet lists sorted alphabetically; concept names
use dotted canonical form so renames produce clean diffs.

### CLI (`enforcer/cli.py`)

Two commands, parallel to `docs` / `sync-doc`:

```python
@cli.command()
@click.option("--config", "config_path", default="enforcer_config")
@click.option("--output", "-o", default=None)
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def graph(config_path, output, fmt):
    """Generate the ontology graph from code."""

@cli.command(name="sync-graph")
@click.option("--config", "config_path", default="enforcer_config")
@click.option("--output", "-o", default="ONTOLOGY.md")
def sync_graph(config_path, output):
    """Regenerate ONTOLOGY.md from code."""
```

`sync-graph` writes the markdown form to `ONTOLOGY.md` by default. `graph`
prints to stdout unless `-o` given; `--format json` for the structured form.

### Check Runner Integration (`enforcer/check_runner.py`)

Mirror the `__rendered_doc__` pattern at `check_runner.py:165`. When any
ontology rule is present, build the graph once per run and stash the fresh
render in `shared_ctx["__rendered_ontology__"]`. `OntologySyncMatcher` reads
it.

Build cost: one AST walk per reachable file (already cached by
`FileContextBuilder`), plus one import-graph build (already cached by
`ImportGraphBuilder`). Net: near-zero overhead when no ontology rule is
configured; one extra render when one is.

## Rules (six, in three families)

All wired into `enforcer_config.py` for self-enforcement.

### Family 1 — Drift

**Rule 1.1: `ontology-graph-sync`** (ERROR, METADATA)

- Matcher: `OntologySyncMatcher` (`enforcer/matchers/ontology_sync.py`).
  Extends the `DocSyncMatcher` pattern.
- Reads `shared_ctx["__rendered_ontology__"]`, compares to on-disk
  `ONTOLOGY.md` at `self.graph_path`.
- Wired as a METADATA rule so it fires once per run regardless of which
  files are staged. A code-only commit (ONTOLOGY.md untouched) still gets
  caught: the fresh render reflects the new code, the on-disk file is
  stale, mismatch flagged.
- Message: `ONTOLOGY.md is stale or missing.`
- Fix instruction: `Run 'enforcer sync-graph' to regenerate ONTOLOGY.md.`

**Rule 1.2: `concept-what-docstring`** (ERROR, CONTENT)

- Matcher: `ConceptDocstringMatcher`
  (`enforcer/matchers/concept_docstring.py`).
- Walks AST for public `class_definition` / `function_definition` nodes (no
  leading `_`), checks the docstring has a `What:` section.
- `needs=AST_PY`, `file_globs=["enforcer/**/*.py"]`,
  `exclude_globs=["**/test*", "**/__init__.py"]`.
- Fires per-symbol, points at the symbol's line.
- Message: `Public symbol '{matched_value}' missing 'What:' docstring section.`
- Fix instruction: `Add a 'What:' line to the docstring describing what this concept is or flags.`

### Family 2 — Boundary rot

**Rule 2.1: `layer-boundaries`** (ERROR, CONTENT)

- Already implemented as `ArchitectureMatcher`. Wire into `enforcer_config.py`
  with this repo's layer map:
  - `types` ← `enforcer/types.py`
  - `core` ← `enforcer/rule.py`, `enforcer/runner.py`, `enforcer/context.py`,
    `enforcer/config.py`, `enforcer/check_runner.py`
  - `matchers` ← `enforcer/matchers/**`
  - `combinators` ← `enforcer/combinators/**`
  - `predicates` ← `enforcer/predicates/**`
  - `extractors` ← `enforcer/extractors/**`
  - `parsers` ← `enforcer/parsers/**`
  - `cli` ← `enforcer/cli.py`, `enforcer/reporter.py`, `enforcer/docs.py`,
    `enforcer/explain.py`, `enforcer/fix.py`, `enforcer/ignore.py`,
    `enforcer/mcp_server.py`
  - `llm` ← `enforcer/llm.py`, `enforcer/matchers/llm_check.py`
  - `graph` ← `enforcer/concept_graph.py`
  - `config` ← `enforcer_config/**`
- `allowed_edges`:
  - `cli -> core`, `cli -> matchers`, `cli -> parsers`, `cli -> graph`,
    `cli -> llm`
  - `core -> types`, `core -> parsers`, `core -> graph`
  - `matchers -> types`, `matchers -> parsers`, `matchers -> combinators`,
    `matchers -> predicates`, `matchers -> extractors`, `matchers -> llm`
  - `combinators -> types`
  - `predicates -> types`
  - `extractors -> types`
  - `llm -> types`
  - `graph -> types`, `graph -> parsers`
  - `config -> types`, `config -> matchers`
- `forbid_implicit=True` (anything not listed is forbidden).
- No new matcher — pure config wiring.

**Rule 2.2: `no-undeclared-shared-ctx-keys`** (ERROR, CONTENT)

- Matcher: `SharedCtxKeyAllowlistMatcher`
  (`enforcer/matchers/shared_ctx_allowlist.py`).
- Scans matcher source files for `shared_ctx.get("..."` and
  `shared_ctx["..."` patterns via regex on the raw text.
- Declared allowlist lives in `enforcer_config.py` as
  `SHARED_CTX_KEYS = {"__import_graph__", "__rendered_doc__",
  "__rendered_ontology__", "__change__", "__public_symbols__",
  "__llm_enabled__", "__llm_config__"}`. Matcher takes the allowlist as a
  field.
- `needs=RAW`, `file_globs=["enforcer/matchers/**/*.py",
  "enforcer/combinators/**/*.py", "enforcer/check_runner.py"]`.
- Message: `shared_ctx key '{matched_value}' is not in the declared allowlist.`
- Fix instruction: `Add the key to SHARED_CTX_KEYS in enforcer_config.py, or remove the access.`

### Family 3 — Index

**Rule 3.1: `ontology-graph-exists`** (ERROR, METADATA)

- Matcher: `FileExistsMatcher` (already exists at
  `enforcer/matchers/file_exists.py`).
- Wired as a METADATA rule, fires once per run if `ONTOLOGY.md` is absent.
- Message: `ONTOLOGY.md does not exist.`
- Fix instruction: `Run 'enforcer sync-graph' to create it.`

**Rule 3.2: `ontology-graph-references-all-public-symbols`** (ERROR, CONTENT)

- Matcher: `GraphCoverageMatcher`
  (`enforcer/matchers/graph_coverage.py`). Two-phase finalizer, like
  `duplicate_code.py`.
- Phase 1 (`find`): no-op. Exists only so the runner registers the
  finalizer. The public-symbol set is populated by `ConceptGraphBuilder`
  into `shared_ctx["__public_symbols__"]` during the graph build.
- Phase 2 (`finalize_duplicates`): after all files processed, compare
  `shared_ctx["__public_symbols__"]` against the concept names in
  `shared_ctx["__rendered_ontology__"]`. Emit a match per symbol present in
  code but absent from the rendered graph.
- If `shared_ctx["__rendered_ontology__"]` is empty (graph build failed or
  no ontology rule triggered the build), skip silently — no false positives.
  Rule 1.1 already flags the missing/stale graph.
- `needs=AST_PY`, `file_globs=["enforcer/**/*.py"]`,
  `exclude_globs=["**/test*"]`, `diff_only=False`.
- Message: `Public symbol '{matched_value}' is missing from ONTOLOGY.md.`
- Fix instruction: `Run 'enforcer sync-graph'. If the symbol is still missing, the graph builder has a parser gap — file a bug.`

## Testing

Per the `AGENTS.md` testing bar: 2 parameterized methods x 3 examples = 6
cases per matcher. Builder tests follow `tests/test_<module>.py` convention.

- `tests/test_concept_graph.py` — builder: extracts symbols, `What:`
  docstrings, layer assignment, import edges, dataclass detection, public
  detection, canonical-name resolution.
- `tests/test_matchers/test_ontology_sync.py` — fresh == on-disk (clean),
  fresh != on-disk (stale), missing file (flag).
- `tests/test_matchers/test_concept_docstring.py` — public symbol with
  `What:` (clean), without `What:` (flag), private symbol (ignored),
  dataclass (still flagged if public + missing `What:`).
- `tests/test_matchers/test_shared_ctx_allowlist.py` — declared key (clean),
  undeclared key (flag), no access (clean), multiple accesses (flag each).
- `tests/test_matchers/test_graph_coverage.py` — symbol in graph (clean),
  symbol missing from graph (flag), private symbol (ignored), empty file
  (clean).

`ArchitectureMatcher` and `FileExistsMatcher` already have tests; the new
work is config wiring only, no new tests needed for those.

## Self-Enforcement

Add all six rules to `enforcer_config.py`. The first commit on this branch
must run `enforcer sync-graph` to seed `ONTOLOGY.md`. After that, drift
blocks commits.

WARN rules for critical-component reminders: `concept_graph.py` is a new
file with broad blast radius (every concept flows through it). Add a WARN
rule firing on edits to `concept_graph.py` reminding the agent to run
`pytest tests/test_concept_graph.py` before acknowledging.

## File Inventory

New files:

- `enforcer/concept_graph.py` — `Concept`, `ConceptGraph`,
  `ConceptGraphBuilder`, `render_ontology_markdown`, `render_ontology_json`.
- `enforcer/matchers/ontology_sync.py` — `OntologySyncMatcher`.
- `enforcer/matchers/concept_docstring.py` — `ConceptDocstringMatcher`.
- `enforcer/matchers/shared_ctx_allowlist.py` —
  `SharedCtxKeyAllowlistMatcher`.
- `enforcer/matchers/graph_coverage.py` — `GraphCoverageMatcher`.
- `tests/test_concept_graph.py`
- `tests/test_matchers/test_ontology_sync.py`
- `tests/test_matchers/test_concept_docstring.py`
- `tests/test_matchers/test_shared_ctx_allowlist.py`
- `tests/test_matchers/test_graph_coverage.py`
- `ONTOLOGY.md` — seeded by `enforcer sync-graph` on first commit.

Modified files:

- `enforcer/cli.py` — add `graph` and `sync-graph` commands.
- `enforcer/check_runner.py` — populate
  `shared_ctx["__rendered_ontology__"]` when an ontology rule is present.
- `enforcer/matchers/__init__.py` — export the four new matchers.
- `enforcer_config/__init__.py` (or `enforcer_config/rules.py`) — add the
  six rules, the layer map, `SHARED_CTX_KEYS`, and the `concept_graph.py`
  WARN rule.
- `AGENTS.md` — document `ConceptGraph`, `ConceptGraphBuilder`, the ontology
  rules, and the `graph` / `sync-graph` commands.
- `CONVENTIONS.md` — regenerated by `enforcer sync-doc` after the new rules
  land.
