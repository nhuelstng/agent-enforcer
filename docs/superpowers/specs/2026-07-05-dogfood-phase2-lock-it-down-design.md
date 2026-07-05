# Dogfood Phase 2: Lock It Down — Design

**Date:** 2026-07-05
**Status:** Approved (Approach B: new matcher + config rules + code fixes)
**Phase:** 2 of 3 (get to green → lock it down → dogfood harder)

## Goal

Prevent the Phase 1 violations from recurring. Add a general
`CanonicalImportMatcher` that enforces "symbol X must be imported from module
Y, not from a re-exporting module." Add config-only rules reusing existing
matchers (config-size cap, scratch-file ban). Fix reviewer findings from
Phase 1.

This phase does **not** include the CI gate (Phase 3) or the config split
(Phase 3).

## Problem

Phase 1 resolved 10 `arch-layer-deps` violations, but nothing prevents them
from recurring:

1. **Re-export hack:** `rule.py` re-exports `glob_match` as `_glob_match`.
   Matchers and `context.py` imported it from `rule.py` (mid-layer) instead of
   `glob_util` (unclassified). The `arch-layer-deps` rule catches the layer
   violation, but only if the re-exported symbol trips a layer edge. A general
   "canonical import" rule catches the pattern directly: "this symbol must
   come from this module."

2. **Config bloat:** `enforcer_config.py` is 823 lines, exempted from
   `file-max-lines` (400). No rule signals when it needs splitting.

3. **Scratch files:** `scratch_violations.py` was committed at repo root,
   triggering `no-print` and `class-capwords`. No rule bans scratch files
   proactively.

4. **Hard-coded `rule_id`:** `DocSyncMatcher` hard-codes
   `rule_id="conventions-md-stale"` in its `Match` objects. The runner
   overwrites this (`rule.py:59` stamps `m.rule_id = self.id`), so it's
   harmless functionally, but misleading — looks like the matcher owns the
   rule_id.

## Design

### Section 1: `CanonicalImportMatcher` (new matcher)

**File:** `enforcer/matchers/canonical_import.py`

```python
@dataclass
class CanonicalImportMatcher:
    """Enforces that symbols are imported from their canonical module.

    What:       flags `from <module> import <symbol>` when <symbol> is in the
                canonical map and <module> is not the canonical source
    Ignores:    imports from the canonical module itself; symbols not in the
                canonical map; `import X` (non-from) statements; files with no AST
    Basis:      AST_PY (walks import_from_statement nodes, extracts module + names)
    shared_ctx: none (defensive default only)
    """
    canonical: dict[str, str]  # {symbol: canonical_module}
    needs: Needs = Needs.AST_PY
```

**Algorithm:**
1. Walk the AST iteratively (DFS, same pattern as `ImportMatcher`).
2. For each `import_from_statement` node:
   - Extract the module path (the first `dotted_name` child).
   - Extract the imported names (subsequent `dotted_name` or `aliased_import`
     children). Handles multi-name imports like `from enforcer.rule import Rule, _glob_match`
     by iterating all imported names — follow the same pattern as
     `ImportGraphBuilder._collect_from_import` (`import_graph.py:132-155`).
   - For each imported name, check if it's in `canonical`.
   - If yes, check if the module matches `canonical[name]`.
   - If not, emit a `Match` with the full import text as `matched_value`.

**Aliased imports:** `from enforcer.rule import _glob_match as gm` — the
imported name is `_glob_match` (the `aliased_import` node wraps a
`dotted_name`). Descend into `aliased_import` children to recover the real
name, same as `ImportGraphBuilder._collect_from_import` does.

**Catches:**
- `from enforcer.rule import glob_match` (symbol in map, wrong module)
- `from enforcer.rule import _glob_match` (alias in map, wrong module)
- Lazy imports inside function bodies (AST walker sees all nodes regardless of
  nesting depth — same as `ImportMatcher`)

**Does NOT catch:**
- `import enforcer.rule` (non-from import — different AST node type, and
  doesn't import a specific symbol)
- `from enforcer.glob_util import glob_match` (correct source — no match)

**Reuses `ImportMatcher` infrastructure:** The AST walking logic
(`_walk_iterative`, `_IMPORT_NODE_TYPES`) is identical to `ImportMatcher`. Two
options:
- (a) Duplicate the ~6-line walk loop (DRY violation but keeps matchers
  independent).
- (b) Extract a shared `_walk_imports(root)` helper into a new
  `import_utils.py` module.

YAGNI — duplicate the 6 lines. Both matchers are small, the walk is trivial,
and extracting a helper for 2 consumers is premature. If a third matcher
needs import walking, extract then.

### Section 2: Config-only rules

Three new rules in `enforcer_config.py`:

**Rule 1: `canonical-import-source`**

Uses `CanonicalImportMatcher`. Bans importing `glob_match`/`_glob_match` from
any module other than `enforcer.glob_util`.

```python
Rule(
    id="canonical-import-source",
    severity=Severity.ERROR,
    matchers=[CanonicalImportMatcher(canonical={
        "glob_match": "enforcer.glob_util",
        "_glob_match": "enforcer.glob_util",
    })],
    file_globs=["enforcer/**/*.py"],
    diff_only=False,
    message="Import {matched_value} from canonical module, not from a re-exporting module.",
    fix_instruction="Import from the canonical source module listed in the canonical map.",
    rationale="Re-exports create hidden coupling. Importing from the canonical low-level module keeps dependencies explicit and prevents arch-layer-deps violations.",
)
```

**Rule 2: `config-size-cap`**

Uses `LineCountMatcher`. WARN (not ERROR) — allows growth but signals when
splitting is needed. 900-line threshold gives ~77 lines of headroom over the
current 823. Phase 3 will split under 400 and remove the `file-max-lines`
exemption.

```python
Rule(
    id="config-size-cap",
    severity=Severity.WARN,
    matchers=[LineCountMatcher(max_lines=900)],
    file_globs=["enforcer_config.py"],
    diff_only=False,
    message="enforcer_config.py is {matched_value} lines — approaching complexity limit (900).",
    fix_instruction="Split rules into separate config modules or reduce rule count.",
    rationale="A monolithic config file is hard to review and maintain. WARN to allow growth, signal when splitting is needed.",
)
```

**Rule 3: `no-scratch-files`**

Uses `AlwaysMatcher`. Any file matching `scratch_*.py` at repo root gets
flagged.

```python
Rule(
    id="no-scratch-files",
    severity=Severity.ERROR,
    matchers=[AlwaysMatcher(matched_value="scratch file at repo root")],
    file_globs=["scratch_*.py"],
    diff_only=False,
    message="Scratch/debug file at repo root: {matched_value}. Delete it.",
    fix_instruction="Delete the file. Use /tmp or a git-ignored directory for scratch work.",
    rationale="Committed scratch files trigger style violations and clutter the repo root.",
)
```

### Section 3: Code fixes (reviewer findings)

**Fix 1: `DocSyncMatcher` hard-coded `rule_id`**

In `enforcer/matchers/doc_sync.py:33`, change:

```python
return [Match(file=file_ctx.path, line=0, rule_id="conventions-md-stale",
```

to:

```python
return [Match(file=file_ctx.path, line=0,
```

The runner stamps `rule_id` from the owning rule (`rule.py:59`), so the
hard-coded value is overwritten anyway. Removing it eliminates confusion.

**Skipped findings (with rationale):**

- **Per-call file read perf:** `conventions-md-stale` is
  `RuleType.METADATA` — runs once per run, not per file. No perf issue.
- **Empty `__rendered_doc__` semantics:** If the rules list is empty, the
  render is empty, and the doc is empty = correctly in sync. The matcher
  can't distinguish "broken pipeline" from "empty rules." That's a caller
  bug, not a matcher bug.

## Verification

After all changes:

```bash
python -m enforcer.cli check --all --config enforcer_config.py
# Expected: No issues found.

pytest --tb=short -q
# Expected: all pass (6+ new tests for CanonicalImportMatcher)

python -m enforcer.cli sync-doc --config enforcer_config.py
# Expected: CONVENTIONS.md updated with 3 new rules
```

## Change summary

| # | Item | Type | Files |
|---|------|------|-------|
| 1 | `CanonicalImportMatcher` | New matcher | `enforcer/matchers/canonical_import.py` + `tests/test_matchers/test_canonical_import.py` |
| 2 | `canonical-import-source` rule | Config | `enforcer_config.py` |
| 3 | `config-size-cap` rule | Config | `enforcer_config.py` |
| 4 | `no-scratch-files` rule | Config | `enforcer_config.py` |
| 5 | `DocSyncMatcher` rule_id fix | Code fix | `enforcer/matchers/doc_sync.py` |
| 6 | Add to `__init__.py` `__all__` | Registration | `enforcer/matchers/__init__.py` |
| 7 | Regenerate `CONVENTIONS.md` | Docs | `CONVENTIONS.md` |

**Total: 2 new files, 4 modified files. 6+ test cases for the new matcher.**

## Out of scope (Phase 3)

- CI gate: `enforcer check --all` must pass on PRs.
- Split `enforcer_config.py` under 400 lines, remove `file-max-lines`
  self-exemption.
- Remove `config-size-cap` WARN rule (superseded by the split + hard cap).
