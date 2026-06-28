# Design Spec: Contract Enforcement for Agent-Driven Codebases

**Date:** 2026-06-28
**Status:** Draft — pending user review
**Target codebase:** TNG/agent-skill-management-library (generalizable)
**Approach:** Extend existing enforcer with two new matchers + TypeScript/Angular extractor support + project rule packs

---

## 1. Problem

Agent-driven coding workflows produce code that passes ruff, eslint, and
actionlint but silently violates **architectural contracts** — implicit
invariants that hold the system together. These contracts are documented in
CLAUDE.md comments and module docstrings, but nothing checks them at commit
time. An agent adding a new `RuleType` enum value without a dispatcher branch,
or a new `@mcp.tool` without a test, ships broken code that linters approve.

### Contract inventory (TNG/agent-skill-management-library)

Six contract families, each grounded in repo fact:

| # | Contract | Evidence | Failure mode |
|---|----------|----------|--------------|
| C1 | Every `@mcp.tool`-decorated function has a test referencing it | 30 tools (`server.py:395-2543`), no per-tool test gate | Agent adds tool, ships untested, breaks agent-e2e silently |
| C2 | Every `RuleType` enum value has a dispatch branch in `_evaluate_deterministic` (`_evaluator.py:469`) or is in `LLM_RULE_TYPES` (`:110`) | 29 enum values (`compliance.py:13-57`), parity unenforced | Agent adds rule type, worker silently skips it |
| C3 | Every `ArtifactKind` enum value has a kind-module under `services/artifact_kinds/` with entry-point validator + install destination | 5 kinds (`artifact.py:47`), registry is source of truth (`backend/CLAUDE.md:9-14`) but completeness unenforced | Agent adds kind, registry misses it, upload 500s |
| C4 | Model integrity constraints (`UniqueConstraint`, `CheckConstraint`, enum values) are not silently weakened in migrations | `artifact.py` has 4+ constraints; `diff_only` filters to added lines, can't detect removals | Agent drops a constraint to unblock a test, data corruption later |
| C5 | Every new `*Config` field syncs all 6 places listed in `config/__init__.py` injection contract | Comment block, not a check | Agent adds config field, dev/prod drift, deploy fails at 3am |
| C6 | REST router and MCP server stay in sync for shared operations | orval codegen is one-directional (frontend only); no MCP↔REST parity check | Agent adds REST route, forgets MCP tool, agent clients can't reach feature |

### Contract inventory — Angular frontend (TNG/agent-skill-management-library)

The frontend has its own contract surface. These are not covered by eslint
(which enforces selector prefix and style) but by project conventions
documented in `frontend/CLAUDE.md`:

| # | Contract | Evidence | Failure mode |
|---|----------|----------|--------------|
| F1 | Every `@Component` has a co-located `.spec.ts` | 64 components, 48 component specs (6 missing: `artifact-card-with-image`, `artifact-image-tile`, 2 `ui/` sub-components, `app.component`, `edit-categories-dialog`) | Agent adds component, ships untested, visual regression undetected |
| F2 | Every `@Component` using `.subscribe()` has a teardown guard (`takeUntilDestroyed()` or `DestroyRef` or `takeUntil`) | 20 files with `.subscribe()` and no teardown guard (of 84 total subscribe calls) | Agent adds subscription, memory leak on route change |
| F3 | Every `@for` in template has a `track` expression | 102 `@for` usages; convention is `track item.id` or `track $index`, but new code may omit it | Agent adds `@for` without `track`, performance regression on large lists |
| F4 | Every lazy-loaded route in `app.routes.ts` has a `canActivate` guard (except public routes: `auth/callback`, `token-login`) | 21 `loadComponent` routes, public routes explicitly unguarded | Agent adds route, forgets guard, auth bypass |
| F5 | Every Angular service is `providedIn: 'root'` (no `@NgModule` providers) | 25 `providedIn` declarations, 0 `@NgModule` (standalone-only codebase) | Agent adds service with component-level provider, singleton contract broken |

### Why existing matchers don't cover this

| Matcher | Closest contract | Why it falls short |
|---------|-----------------|-------------------|
| `PairedFileMatcher` | C1 (tool→test) | 1:1 file existence via `{stem}` substitution. Can't iterate decorated function names or enum values. |
| `FileExistsMatcher` + `Not` | C1 (global test existence) | Checks if ANY test file exists, not if a test for THIS specific tool exists. Can't tie to symbols in the source file. |
| `AllowlistMatcher` | C2 (enum→dispatch) | Wrong direction: checks if file-under-test's content is IN the allowlist. C2 needs: symbols DEFINED in file A must APPEAR in file B. |
| `DuplicateCodeMatcher` | — | Right two-phase shape (`find()` collects, `finalize_duplicates()` runs after all files), but wrong semantic (n-gram similarity, not symbol presence). |
| `diff_only` flag | C4 (constraint removal) | Filters to added lines only. Cannot detect that a constraint was REMOVED from a migration. |

**Verdict:** Two new matcher types genuinely needed. No existing composition covers C1-C5. C6 is a semantic parity check better suited to CI than pre-commit.

---

## 2. Design

### 2.1 Two new matchers

#### Matcher A: `SymbolPresenceMatcher` (covers C1, C2, C3, C5)

**Purpose:** Extract symbols from the file-under-test (source), then verify each
symbol appears in at least one reference file matching a glob.

**Shape:**
```python
@dataclass
class SymbolPresenceMatcher:
    """Two-phase: find() collects symbols from source file into shared_ctx.
    finalize_presence() runs after all files processed, checks each symbol
    against reference files. Emits a Match for each symbol not found in any
    reference file."""
    extractor: Callable[[FileContext], list[str]]  # extracts symbols from source
    reference_glob: str                            # glob for reference files
    needs: Needs = Needs.AST_TS                    # AST needed for extraction

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        # Phase 1: extract symbols from source file, store in shared_ctx
        # Returns [] (no matches yet — finalize phase emits)

    def finalize_presence(self, shared_ctx: dict) -> list[Match]:
        # Phase 2: for each symbol collected, check if it appears in any
        # reference file (already loaded into shared_ctx via read_targets
        # or globbed here). Emit Match for missing symbols.
```

**How it maps to contracts:**

| Contract | `extractor` | `reference_glob` |
|----------|-------------|-------------------|
| C1 (tool→test) | Extract `@mcp.tool`-decorated function names from `server.py` | `backend/tests/**/*.py` |
| C2 (enum→dispatch) | Extract enum values from `RuleType` class in `compliance.py` | `backend/app/jobs/_evaluator.py` |
| C3 (kind→module) | Extract `ArtifactKind` enum values from `artifact.py` | `backend/app/services/artifact_kinds/*.py` |
| C5 (config sync) | Extract `*Config` field names from `config/__init__.py` | `.env.config`, `.env.config.example`, `infrastructure/aws/service/*/main.tf` |

**Why two-phase (like `DuplicateCodeMatcher`):** The matcher must collect
symbols from the source file, then check them against reference files that may
not be in the staged set. The two-phase shape (`find()` collects into
`shared_ctx`, finalizer runs after all files processed) is already proven by
`DuplicateCodeMatcher` and hooks into `run_cross_file_finalizers()` in the
runner.

**Extractor is a callable, not a built-in:** Different contracts extract
different symbols (decorated functions vs enum values vs config field names).
A callable extractor keeps the matcher generic; project rule packs provide
project-specific extractors.

**Reference file loading:** Two options:
1. **Via `read_targets`** — already supported. The rule declares
   `reference_glob` as a `read_target`, the CLI loads it into `shared_ctx`,
   the matcher reads from there. Pro: no new loading code. Con: `read_targets`
   loads files as `FileContext` objects with `raw` text, but this matcher
   needs to grep across multiple files — the `shared_ctx` is keyed by glob
   string, so only one file per glob.
2. **Via direct glob in finalizer** — the matcher globs `reference_glob`
   itself in `finalize_presence()`, reads each file, greps for symbols. Pro:
   handles multiple reference files. Con: duplicates file-loading logic.

**Decision: Option 2 (direct glob in finalizer).** The matcher owns its
reference-file loading because it needs to scan MULTIPLE files (e.g. all test
files for C1, all kind-modules for C3). `read_targets` is 1:1 keyed and
can't express "all test files." The `DuplicateCodeMatcher` precedent supports
this — it reads from `shared_ctx` but that's because all files are already
loaded into it by the runner's file loop. For reference files NOT in the
staged set, direct glob is necessary.

#### Matcher B: `DiffRemovalMatcher` (covers C4)

**Purpose:** Detect that specific patterns were REMOVED from a staged file
relative to HEAD. Complements `diff_only` (which filters to added lines).

**Shape:**
```python
@dataclass
class DiffRemovalMatcher:
    """Parses git diff --cached for REMOVED lines matching a pattern.
    Emits a Match for each removed line that matched the pattern."""
    pattern: str  # regex
    needs: Needs = Needs.RAW  # needs raw to parse diff hunk headers

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        # Run `git diff --cached -U0 -- {file}` 
        # Parse removed lines (lines starting with `-` but not `---`)
        # Match each against self.pattern
        # Emit Match with line=0, matched_value=removed text
```

**How it maps to C4:**
- Pattern: `UniqueConstraint|CheckConstraint|unique=True|Index\(`
- If any of these appear in REMOVED lines of a migration file, flag it.
- The agent must explicitly justify constraint removal (WARN severity, blocks
  until confirmed via `--confirm-read-warnings`).

**Why a separate matcher, not a flag on existing matchers:** `diff_only`
filters matches to changed lines. This matcher operates on the diff itself,
not the file content. A `RegexMatcher` with `diff_only=True` would check if
a pattern matches on ADDED lines; we need the opposite — patterns on REMOVED
lines. The semantics are fundamentally different.

### 2.2 TypeScript and Angular support

The enforcer already parses TypeScript ASTs via tree-sitter
(`tree_sitter.py:33-39`, `Needs.AST_TS`). The `SymbolPresenceMatcher` works
on any tree-sitter AST — the extractor callable receives a `FileContext`
with `.ast` populated for `.ts`/`.tsx` files. No parser changes needed.

What IS needed: **TypeScript/Angular-specific reference extractors** in
`enforcer/extractors/typescript.py`. These are the TS equivalents of the
Python extractors in §4, walking the TypeScript tree-sitter grammar instead
of the Python grammar:

```python
# enforcer/extractors/typescript.py — reference examples, not auto-loaded

def decorated_methods(decorator_name: str):
    """TS: find method names decorated with @decorator_name.
    Tree-sitter: method_definition with decorator ancestors."""
    ...

def class_names(pattern: str = ".*Component$"):
    """TS: find @Component class names matching pattern.
    Tree-sitter: class_declaration with decorator matching @Component."""
    ...

def subscribe_calls_without_teardown():
    """TS: find .subscribe() calls NOT preceded by takeUntilDestroyed/
    takeUntil/DestroyRef in the same lexical scope.
    Two-pass: collect subscribe locations, collect teardown references,
    emit for subscribes with no nearby teardown."""
    ...

def for_without_track():
    """Angular template (inline): find @for blocks missing track expression.
    Uses the inline template source extracted from the @Component decorator."""
    ...
```

**Why these are extractors, not matchers:** An extractor's job is to produce
a list of symbol strings (or locations). The matcher's job is to check
presence/absence. F2 (subscribe without teardown) and F3 (`@for` without
`track`) are **single-file contracts** — they don't need cross-file presence
checking. They fit better as standalone matchers or as an
`AstNodeMatcher` + predicate combination. The extractors above are for
cross-file contracts (F1: component→spec, F4: route→guard, F5:
service→providedIn).

| Frontend contract | Extractor (for SymbolPresenceMatcher) or standalone matcher? |
|-------------------|--------------------------------------------------------------|
| F1 (component→spec) | `SymbolPresenceMatcher` + `class_names(".*Component$")` extractor, reference_glob = co-located `*.spec.ts` |
| F2 (subscribe teardown) | Standalone AST matcher (single-file, structural) — see §2.5 |
| F3 (`@for` track) | Standalone template matcher (single-file, inline template) — see §2.5 |
| F4 (route→guard) | `SymbolPresenceMatcher` + route-path extractor, reference_glob = `app.routes.ts` (or vice versa) |
| F5 (providedIn root) | `RegexMatcher` with `providedIn:` + predicate (single-file, already enforceable) |

### 2.3 Project rule packs

The enforcer already supports per-project config via `enforcer_config.py`.
Rule packs for the TNG codebase live in the TNG repo, not the enforcer repo.

**Location:** `.enforcer/rules.py` in the target repo, loaded by the existing
`load_config()` mechanism (executes the module, extracts `RULES`).

**Example rule pack (illustrative — backend + frontend):**

```python
from enforcer import Rule, Severity
from enforcer.matchers import SymbolPresenceMatcher, DiffRemovalMatcher
from enforcer.extractors.python import decorated_functions, enum_values
from enforcer.extractors.typescript import class_names

RULES = [
    # --- Backend contracts (C1-C4) ---
    Rule(
        id="mcp-tool-has-test",
        severity=Severity.ERROR,
        matchers=[SymbolPresenceMatcher(
            extractor=decorated_functions("mcp.tool"),
            reference_glob="backend/tests/**/*.py",
        )],
        file_globs=["backend/app/mcp/server.py"],
        message="MCP tool '{matched_value}' has no test. Add a test referencing it.",
        fix_instruction="Create or update a test in backend/tests/ that calls this tool.",
    ),
    Rule(
        id="rule-type-has-dispatcher",
        severity=Severity.ERROR,
        matchers=[SymbolPresenceMatcher(
            extractor=enum_values("RuleType"),
            reference_glob="backend/app/jobs/_evaluator.py",
        )],
        file_globs=["backend/app/models/compliance.py"],
        message="RuleType '{matched_value}' has no dispatch branch in _evaluator.py.",
        fix_instruction="Add a branch in _evaluate_deterministic or add to LLM_RULE_TYPES.",
    ),
    Rule(
        id="no-constraint-removal-in-migration",
        severity=Severity.WARN,
        matchers=[DiffRemovalMatcher(
            pattern=r"UniqueConstraint|CheckConstraint|unique=True|Index\(",
        )],
        file_globs=["backend/alembic/versions/*.py"],
        message="Constraint '{matched_value}' removed in migration. Confirm this is intentional.",
        fix_instruction="If intentional, acknowledge with --confirm-read-warnings. Otherwise restore the constraint.",
    ),

    # --- Frontend contracts (F1, F4) ---
    Rule(
        id="component-has-spec",
        severity=Severity.WARN,
        matchers=[PairedFileMatcher(
            source_glob="**/*.component.ts",
            derived_glob="{stem}.spec.ts",
        )],
        file_globs=["frontend/src/**/*.component.ts"],
        exclude_globs=["**/generated/**"],
        message="Component '{file}' has no co-located .spec.ts. Agents must write tests.",
        fix_instruction="Create a .spec.ts file alongside the component.",
    ),
    Rule(
        id="service-provided-in-root",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"@Injectable\(\s*\{(?!\s*providedIn)")],
        file_globs=["frontend/src/**/*.service.ts"],
        message="Service '{file}' must be providedIn: 'root'. No @NgModule providers.",
        fix_instruction="Add providedIn: 'root' to the @Injectable decorator.",
    ),
]
```

### 2.3 Integration with existing pre-commit config

The enforcer hooks into the existing `.pre-commit-config.yaml` as a local hook:

```yaml
  - repo: local
    hooks:
      - id: enforcer-contracts
        name: enforcer (architectural contracts)
        language: system
        entry: python -m enforcer.cli check --staged --config .enforcer/rules.py
        pass_filenames: false
        files: ^(backend/app/mcp/server\.py|backend/app/models/compliance\.py|backend/app/models/artifact\.py|backend/app/jobs/_evaluator\.py|backend/alembic/versions/.*\.py|frontend/src/.*\.component\.ts|frontend/src/.*\.service\.ts)$
```

`pass_filenames: false` because the enforcer reads staged files itself via
`--staged`. The `files` regex limits when the hook fires (only when
contract-bearing files change).

### 2.4 Generalization

The two matchers are generic — not specific to TNG:

| Matcher | Generic pattern | Any codebase with... |
|---------|----------------|----------------------|
| `SymbolPresenceMatcher` | "symbols defined in file A must appear in files matching glob B" | Registry-and-dispatcher (C2), public-API-needs-test (C1), plugin-system-completeness (C3), config-injection-contract (C5), component→spec (F1) |
| `DiffRemovalMatcher` | "patterns matching X must not appear in removed lines of files matching glob Y" | Migration safety (C4), API-removal-detection, security-control-removal |

The extractors are project-specific callables. The matchers are not.

### 2.5 Framework-specific rules — extension point

The enforcer ships extractors under `enforcer/extractors/`:
- `python.py` — `decorated_functions()`, `enum_values()`, `config_fields()`
- `typescript.py` — `class_names()`, `decorated_methods()`

These are **reference implementations**, not auto-loaded. Project rule packs
import what they need or write their own. The extractor signature is fixed:
`(FileContext) -> list[str]`.

**Angular-specific rules that need new matchers (not just extractors):**

F2 (subscribe without teardown) and F3 (`@for` without `track`) are
**single-file structural checks** — they don't fit `SymbolPresenceMatcher`
(which is cross-file). Two options:

1. **`AstNodeMatcher` + custom predicate** — walk the AST for
   `call_expression` nodes whose text contains `.subscribe()`, then check
   the surrounding lexical scope for `takeUntilDestroyed`/`DestroyRef`.
   Doable with existing matchers + a custom predicate, but the predicate
   is complex (scope analysis).

2. **New `SubscribeTeardownMatcher`** — purpose-built for this contract.
   Simpler to author, but Angular-specific.

**Decision: defer F2 and F3 to a framework-rules package.** The design ships
with the two cross-file matchers (`SymbolPresenceMatcher`,
`DiffRemovalMatcher`) and the extractor extension point. F2/F3 land as
follow-up work under `enforcer/frameworks/angular/`:

```
enforcer/
  extractors/
    python.py       # reference extractors
    typescript.py   # reference extractors
  frameworks/
    __init__.py
    angular/
      __init__.py
      matchers.py   # SubscribeTeardownMatcher, ForTrackMatcher
      rules.py      # pre-built Angular rules (F2, F3, F5)
```

A project rule pack can import from `enforcer.frameworks.angular` instead of
writing rules from scratch. This is the extension point for future framework
rules — React, Vue, Svelte can each get a sub-package with framework-specific
matchers and pre-built rules.

**Why not ship framework rules now:** YAGNI. The TNG frontend's highest-value
contracts are F1 (component→spec, covered by `PairedFileMatcher`) and F5
(providedIn:root, covered by `RegexMatcher`). Both are already enforceable
with existing matchers. F2/F3 are real contracts but lower-value — they're
performance/dead-code issues, not correctness bugs. Ship the extension point
(empty `frameworks/` package with `__init__.py`), populate when needed.

---

## 3. Runner integration

### 3.1 `SymbolPresenceMatcher` finalizer hook

The runner already calls `run_cross_file_finalizers()` which checks for
`finalize_duplicates()` on matchers. Add a parallel check for
`finalize_presence()`:

```python
# runner.py — extend run_cross_file_finalizers
for matcher in rule.matchers:
    if hasattr(matcher, "finalize_duplicates"):
        matches = matcher.finalize_duplicates(shared_ctx)
        ...
    if hasattr(matcher, "finalize_presence"):  # NEW
        matches = matcher.finalize_presence(shared_ctx)
        for m in matches:
            m.rule_id = rule.id
            m.severity = rule.severity
            m.fix_instruction = rule.fix_instruction
            m.message = rule._render_message(m)
        all_matches.extend(matches)
```

**Lazy alternative:** Use `getattr(matcher, "finalize_presence", None)` instead
of `hasattr` — same cost, more Pythonic. But `hasattr` is consistent with the
existing `finalize_duplicates` pattern. Keep consistency.

### 3.2 `DiffRemovalMatcher` — no runner changes needed

It's a standard single-file matcher. Its `find()` runs `git diff --cached`
directly (like `branch_name.py` and `commit_message.py` run git commands).
No finalizer needed — it emits matches in the normal per-file pass.

**Workspace handling:** Like `branch_name.py`, it uses `self.workspace` as
the git cwd.

---

## 4. Extractor authoring

Extractors are callables `(FileContext) -> list[str]`. The enforcer ships
**reference extractors** under `enforcer/extractors/` for Python and
TypeScript — importable but not mandatory. Project rule packs can define
their own inline.

### 4.1 Python extractors (`enforcer/extractors/python.py`)

```python
# enforcer/extractors/python.py — reference examples, not auto-loaded

def decorated_functions(decorator_name: str):
    """Returns an extractor that finds function names decorated with @decorator_name."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast:
            return []
        # Walk tree-sitter AST for decorated_function_definition nodes
        # where decorator text matches @decorator_name
        # Return list of function name strings
    return extract

def enum_values(class_name: str):
    """Returns an extractor that finds enum values from a StrEnum class."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast:
            return []
        # Walk AST for class_definition named class_name
        # Collect assignment values
    return extract

def config_fields(class_suffix: str = "Config"):
    """Returns an extractor that finds field names from dataclasses ending in 'Config'."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast:
            return []
        # Walk AST for class_definition matching *Config
        # Collect annotated assignment names
    return extract
```

### 4.2 TypeScript extractors (`enforcer/extractors/typescript.py`)

```python
# enforcer/extractors/typescript.py — reference examples, not auto-loaded

def class_names(pattern: str = ".*"):
    """Returns an extractor that finds @Component/@Directive/@Pipe class names matching a regex.
    Used for F1 (component→spec): extract class names, check if a co-located
    .spec.ts references them."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast:
            return []
        # Walk tree-sitter AST for class_declaration nodes
        # where the class has a decorator matching @Component/@Directive/@Pipe
        # and the class name matches `pattern`
        # Return list of class name strings
    return extract

def decorated_methods(decorator_name: str):
    """Returns an extractor that finds method names decorated with @decorator_name.
    Used for Angular lifecycle hooks or custom decorators."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast:
            return []
        # Walk AST for method_definition nodes with decorator ancestors
        # matching @decorator_name
    return extract

def route_paths():
    """Returns an extractor that finds lazy-loaded route paths from an
    Angular routes file. Used for F4 (route→guard): extract path strings,
    check if each route has a canActivate guard."""
    def extract(ctx: FileContext) -> list[str]:
        if not ctx.ast or not ctx.raw:
            return []
        # The routes file uses `loadComponent` + `canActivate` object literals.
        # Walk AST for property assignments under the routes array,
        # collect `path:` values where `loadComponent` is present and
        # `canActivate` is absent.
    return extract
```

**Tree-sitter TypeScript grammar:** The enforcer already loads
`tree_sitter_typescript` (`tree_sitter.py:33-39`). The grammar node types
for TypeScript are: `class_declaration`, `method_definition`,
`decorator`, `property_signature`, `call_expression`. These are stable
tree-sitter node names, not enforcer-specific.

---

## 5. C6 (API/MCP parity) — out of scope for enforcer

C6 requires **semantic mapping** between REST routes and MCP tools (e.g.
`POST /api/artifacts` corresponds to `save_and_publish_local_artifact`).
This is not a pattern-matching problem — it requires understanding the
mapping convention, which lives in developer heads and CLAUDE.md prose.

**Recommendation:** C6 is a CI check, not a pre-commit check. A separate
test that introspects the FastAPI router and the MCP server, builds a mapping
table, and asserts parity. This belongs in `backend/tests/` as an integration
test, not in the enforcer.

---

## 6. Test plan

### 6.1 `SymbolPresenceMatcher` tests

| Test | Setup | Assertion |
|------|-------|-----------|
| Symbol present in reference file | Source with `@mcp.tool def foo()`, reference file containing `foo` | No matches |
| Symbol absent from reference files | Source with `@mcp.tool def bar()`, reference file without `bar` | One Match, `matched_value="bar"` |
| Multiple symbols, partial presence | Source with 3 symbols, reference has 2 | One Match for the missing symbol |
| No symbols extracted | Source with no decorated functions | No matches |
| Reference glob matches no files | Any source, `reference_glob="nonexistent/**"` | No matches (degraded — see §7) |
| Two-phase: symbols collected before finalize | Run `find()` on source, then `finalize_presence()` | Matches only emitted in finalize phase |
| Shared_ctx isolation | Two rules with different `SymbolPresenceMatcher` instances | Symbols don't cross-contaminate |

### 6.2 `DiffRemovalMatcher` tests

| Test | Setup | Assertion |
|------|-------|-----------|
| Pattern removed | Staged diff with `-    UniqueConstraint(...)` | One Match |
| Pattern added (not removed) | Staged diff with `+    UniqueConstraint(...)` | No matches |
| Pattern not in diff | Staged diff with unrelated changes | No matches |
| Multiple removals | Staged diff removing 2 constraint patterns | Two Matches |
| No diff (file unchanged) | File not staged or no changes | No matches |
| Non-matching removed line | Staged diff removing `-    return 42` | No matches |

### 6.3 Integration test (TNG rule pack)

| Test | Setup | Assertion |
|------|-------|-----------|
| C1: tool without test | `server.py` with `@mcp.tool def new_tool()`, no test references `new_tool` | ERROR match |
| C2: enum without dispatcher | `compliance.py` with new `RuleType.foo`, `_evaluator.py` without `foo` | ERROR match |
| C4: constraint removed in migration | Migration removing `UniqueConstraint` | WARN match |

### 6.4 TypeScript extractor tests

| Test | Setup | Assertion |
|------|-------|-----------|
| `class_names` extracts `@Component` classes | TS file with `@Component() class FooComponent` | Returns `["FooComponent"]` |
| `class_names` with pattern filter | TS file with `FooComponent` and `BarService`, pattern `.*Component$` | Returns `["FooComponent"]` only |
| `decorated_methods` finds decorated methods | TS file with `@ViewChild() method foo()` | Returns `["foo"]` |
| `route_paths` extracts unguarded paths | `app.routes.ts` with route `{ path: 'admin', loadComponent: ... }` (no `canActivate`) | Returns `["admin"]` |
| `route_paths` skips guarded routes | Same file with `{ path: 'secure', canActivate: [authGuard], loadComponent: ... }` | Does not return `"secure"` |
| AST unavailable | `ctx.ast is None` | Returns `[]` (degraded) |

---

## 7. Edge cases and degradation

| Case | Behavior | Rationale |
|------|----------|-----------|
| Reference glob matches no files | No matches emitted (silent) | Can't enforce presence against void; better to skip than false-positive |
| Source file not in staged set | Matcher doesn't run | `file_globs` + staged-file filter handles this |
| AST parse fails | Extractor returns `[]` | Degraded: no symbols extracted, no matches. Better than crash. |
| `finalize_presence()` called before any `find()` | Returns `[]` | `shared_ctx` empty, no symbols to check |
| Same symbol appears in multiple reference files | No match (found in at least one) | "at least one" is the contract |
| DiffRemovalMatcher on binary file | No matches | `git diff` returns binary marker, regex finds nothing |

---

## 8. Non-goals

- **C6 (API/MCP parity)** — semantic, not pattern-based. CI test, not enforcer.
- **Auto-fixing missing tests/dispatchers** — fix instructions are text only (consistent with existing design).
- **Enforcing contract correctness** (only presence) — the matcher checks that a symbol APPEARS in reference files, not that the reference is semantically correct. A test that mentions `foo` in a comment would pass C1. This is a known limitation; the contract is "presence," not "correctness."
- **Cross-repo contracts** — the enforcer operates within one workspace. Contracts spanning multiple repos are out of scope.

---

## 9. File impact

| File | Change |
|------|--------|
| `enforcer/matchers/symbol_presence.py` | NEW — `SymbolPresenceMatcher` |
| `enforcer/matchers/diff_removal.py` | NEW — `DiffRemovalMatcher` |
| `enforcer/matchers/__init__.py` | Export new matchers |
| `enforcer/runner.py` | Add `finalize_presence()` check in `run_cross_file_finalizers()` |
| `enforcer/extractors/__init__.py` | NEW — package init |
| `enforcer/extractors/python.py` | NEW — Python reference extractors |
| `enforcer/extractors/typescript.py` | NEW — TypeScript reference extractors |
| `enforcer/frameworks/__init__.py` | NEW — empty extension point |
| `enforcer/frameworks/angular/__init__.py` | NEW — empty extension point |
| `tests/test_matchers/test_symbol_presence.py` | NEW — unit tests |
| `tests/test_matchers/test_diff_removal.py` | NEW — unit tests |
| `tests/test_extractors/test_python.py` | NEW — extractor tests |
| `tests/test_extractors/test_typescript.py` | NEW — extractor tests |
| `tests/test_integration.py` | Add contract-enforcement integration test |

**Total: 10 new files, 2 modified files.** No changes to `Rule`, `FileContext`,
`Config`, or `CLI` — the design reuses existing extension points
(`shared_ctx`, finalizers, `file_globs`, `read_targets`).

---

## 10. Open questions

1. **`finalize_presence` vs. unifying on `finalize_duplicates`:** Should
   `SymbolPresenceMatcher` reuse the `finalize_duplicates` method name to
   avoid adding a second finalizer check? **Lean: no** — the method name
   `finalize_duplicates` is misleading for presence checks. A second
   `hasattr` check is 2 lines; the clarity is worth it.

2. **Reference file caching:** If `reference_glob` matches 50 test files,
   `finalize_presence()` reads all 50. Should results be cached in
   `shared_ctx` across multiple `SymbolPresenceMatcher` instances? **Lean:
   no** — YAGNI until measured. Pre-commit runs on staged files only; if
   `server.py` is staged, there's one matcher instance, one finalizer call.

3. **C4 scope:** Should `DiffRemovalMatcher` also flag removal of
   `nullable=False`, foreign key `ondelete` clauses, or index column
   changes? **Lean: start narrow** — `UniqueConstraint|CheckConstraint|
   unique=True|Index\(`. Expand when a real failure mode demonstrates need.

4. **Severity for C1/C2/C3/F1/F5:** ERROR (blocks commit) or WARN (blocks until
   confirmed)? **Lean: ERROR for C1/C2** (untested tools and undispached
   enum values are real bugs), **WARN for C3** (kind-module completeness
   may have legitimate partial implementations during development),
   **WARN for F1** (component→spec, the codebase has 6 existing violations),
   **ERROR for F5** (providedIn:root is a hard convention, zero exceptions).

5. **F2/F3 framework matchers:** When should we implement
   `SubscribeTeardownMatcher` and `ForTrackMatcher`? **Lean: after the core
   matchers ship and the TNG rule pack is in use.** The `frameworks/angular/`
   package exists as an extension point from day one; populate when a real
   agent-introduced regression demonstrates the need.
