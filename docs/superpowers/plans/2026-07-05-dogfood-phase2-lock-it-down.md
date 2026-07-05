# Dogfood Phase 2: Lock It Down — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Phase 1 violations from recurring by adding a `CanonicalImportMatcher` (enforces canonical import sources), three new config rules (canonical-import-source, config-size-cap, no-scratch-files), and fixing the `DocSyncMatcher` hard-coded `rule_id`.

**Architecture:** New `CanonicalImportMatcher` walks the AST for `import_from_statement` nodes, extracts module + imported names, and flags symbols imported from non-canonical modules. Config rules reuse existing matchers (`LineCountMatcher`, `AlwaysMatcher`). One 1-line code fix in `doc_sync.py`.

**Tech Stack:** Python 3.11+, pytest, tree-sitter. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-05-dogfood-phase2-lock-it-down-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `enforcer/matchers/canonical_import.py` | `CanonicalImportMatcher` | Create |
| `tests/test_matchers/test_canonical_import.py` | Tests for new matcher | Create |
| `enforcer/matchers/__init__.py` | Matcher registry | Modify: add import + `__all__` entry |
| `enforcer_config.py` | Self-enforcement config | Modify: add 3 rules + import |
| `enforcer/matchers/doc_sync.py` | DocSyncMatcher | Modify: remove hard-coded `rule_id` |
| `CONVENTIONS.md` | Generated docs | Regenerate |

---

## Task 1: Write `CanonicalImportMatcher`

**Files:**
- Create: `enforcer/matchers/canonical_import.py`

This matcher walks the AST for `import_from_statement` nodes, extracts the module path and imported names, and flags any symbol that's imported from a non-canonical module. It reuses the iterative DFS walk pattern from `ImportMatcher` and the multi-name extraction logic from `ImportGraphBuilder._collect_from_import`.

- [ ] **Step 1: Write the matcher**

Create `enforcer/matchers/canonical_import.py`:

```python
"""CanonicalImportMatcher: enforces symbols are imported from their canonical module."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class CanonicalImportMatcher:
    """Enforces that symbols are imported from their canonical module, not re-exporting modules.

    What:       flags `from <module> import <symbol>` when <symbol> is in the canonical map
                and <module> is not the canonical source
    Ignores:    imports from the canonical module itself; symbols not in the canonical map;
                `import X` (non-from) statements; files with no AST; relative imports
    Basis:      AST_PY (walks import_from_statement nodes, extracts module + imported names)
    shared_ctx: none (defensive default only)
    """
    canonical: dict[str, str]
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Walk AST for import_from_statement nodes, flag non-canonical imports. Returns list of Match."""
        if not file_ctx.ast:
            return []
        from enforcer.parsers.ast_utils import walk_ast, node_text

        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type != "import_from_statement":
                continue
            module, names = self._extract_module_and_names(node, node_text)
            if module is None or not names:
                continue
            for name in names:
                canonical_module = self.canonical.get(name)
                if canonical_module is not None and module != canonical_module:
                    text = node_text(node)
                    if isinstance(text, bytes):
                        text = text.decode()
                    matches.append(Match(
                        file=file_ctx.path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1] + 1,
                        matched_value=text.strip(),
                    ))
                    break  # one match per import statement is enough
        return matches

    @staticmethod
    def _extract_module_and_names(node, node_text) -> tuple[str | None, list[str]]:
        """Extract module path and imported names from an import_from_statement node.

        Handles multi-name imports like `from enforcer.rule import Rule, _glob_match`
        and aliased imports like `from enforcer.rule import _glob_match as gm`.
        Follows the same pattern as ImportGraphBuilder._collect_from_import.
        """
        children = node.children
        dotted_names = [c for c in children if c.type == "dotted_name"]
        relative = [c for c in children if c.type == "relative_import"]
        if relative or not dotted_names:
            return None, []

        module = node_text(dotted_names[0])
        if isinstance(module, bytes):
            module = module.decode()

        imported_nodes = dotted_names[1:] + [c for c in children if c.type == "aliased_import"]
        if not imported_nodes:
            return module, []

        names: list[str] = []
        for name_node in imported_nodes:
            if name_node.type == "aliased_import":
                sub = next((cc for cc in name_node.children if cc.type == "dotted_name"), None)
                if sub is None:
                    continue
                name_node = sub
            name = node_text(name_node)
            if isinstance(name, bytes):
                name = name.decode()
            names.append(name)
        return module, names
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from enforcer.matchers.canonical_import import CanonicalImportMatcher; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add enforcer/matchers/canonical_import.py
git commit -s -m "feat(matchers): add CanonicalImportMatcher

Enforces that symbols are imported from their canonical module, not from
re-exporting modules. Walks AST for import_from_statement nodes, extracts
module + imported names (handles multi-name and aliased imports), flags
symbols in the canonical map that come from a non-canonical module.

Prevents the Phase 1 regression where matchers imported _glob_match from
enforcer.rule instead of enforcer.glob_util."
```

---

## Task 2: Write tests for `CanonicalImportMatcher`

**Files:**
- Create: `tests/test_matchers/test_canonical_import.py`

Per repo convention (`matcher-test-positive-negative` rule): 2 parameterized test classes (positive + negative), each with ≥3 cases.

- [ ] **Step 1: Write the test file**

Create `tests/test_matchers/test_canonical_import.py`:

```python
"""Tests for CanonicalImportMatcher: enforces symbols imported from canonical module."""
import pytest
from enforcer.matchers.canonical_import import CanonicalImportMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "test.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_CANONICAL = {"glob_match": "enforcer.glob_util", "_glob_match": "enforcer.glob_util"}


class TestCanonicalImportFlags:
    """flags symbols imported from non-canonical modules."""

    @pytest.mark.parametrize("source", [
        "from enforcer.rule import glob_match\n",
        "from enforcer.rule import _glob_match\n",
        "from enforcer.rule import glob_match as gm\n",
    ])
    def test_flags_non_canonical(self, source):
        ctx = _make_ctx(source)
        matcher = CanonicalImportMatcher(canonical=_CANONICAL)
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert "glob_match" in matches[0].matched_value

    @pytest.mark.parametrize("source", [
        "from enforcer.rule import Rule, _glob_match\n",
        "from enforcer.rule import _glob_match, Rule\n",
        "from enforcer.rule import Rule as R, _glob_match as gm\n",
    ])
    def test_flags_in_multi_name_import(self, source):
        ctx = _make_ctx(source)
        matcher = CanonicalImportMatcher(canonical=_CANONICAL)
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert "glob_match" in matches[0].matched_value


class TestCanonicalImportClean:
    """does not flag imports from the canonical module or symbols not in the map."""

    @pytest.mark.parametrize("source", [
        "from enforcer.glob_util import glob_match\n",
        "from enforcer.glob_util import glob_match as _glob_match\n",
        "from enforcer.rule import Rule\n",
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        matcher = CanonicalImportMatcher(canonical=_CANONICAL)
        assert matcher.find(ctx) == []


def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="from enforcer.rule import glob_match")
    matcher = CanonicalImportMatcher(canonical=_CANONICAL)
    assert matcher.find(ctx) == []


def test_needs_ast_py():
    """Should declare AST_PY as its needs."""
    matcher = CanonicalImportMatcher(canonical={})
    assert matcher.needs == Needs.AST_PY
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_matchers/test_canonical_import.py --tb=short -q`

Expected: all pass (8 tests: 3+3 parametrized + 2 standalone).

- [ ] **Step 3: Verify test coverage rule passes**

Run: `python -m enforcer.cli check --paths tests/test_matchers/test_canonical_import.py --config enforcer_config.py 2>&1 | tail -5`

Expected: `No issues found.` (the `matcher-test-positive-negative` rule should pass — 2 parametrized classes, each with ≥3 cases).

- [ ] **Step 4: Commit**

```bash
git add tests/test_matchers/test_canonical_import.py
git commit -s -m "test(matchers): add tests for CanonicalImportMatcher

8 tests: 3 positive (flags non-canonical), 3 positive (flags in multi-name
imports), 3 negative (clean imports from canonical module + symbols not in
map), 2 standalone (no AST, needs declaration). Parameterized per repo
convention."
```

---

## Task 3: Register `CanonicalImportMatcher` in `__init__.py`

**Files:**
- Modify: `enforcer/matchers/__init__.py`

- [ ] **Step 1: Add import and `__all__` entry**

In `enforcer/matchers/__init__.py`:

After line 11 (`from enforcer.matchers.import_matcher import ImportMatcher`), add:

```python
from enforcer.matchers.canonical_import import CanonicalImportMatcher
```

In the `__all__` list, after `"ArchitectureMatcher",` (line 38), add:

```python
    "CanonicalImportMatcher",
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from enforcer.matchers import CanonicalImportMatcher; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add enforcer/matchers/__init__.py
git commit -s -m "feat(matchers): register CanonicalImportMatcher in __init__"
```

---

## Task 4: Add `canonical-import-source` rule to config

**Files:**
- Modify: `enforcer_config.py`

- [ ] **Step 1: Add import**

In `enforcer_config.py`, in the `from enforcer.matchers import (...)` block (lines 26-50). After `ArchitectureMatcher,` (line 47), add:

```python
    CanonicalImportMatcher,
```

- [ ] **Step 2: Add the rule**

After the `no-private-cross-import` rule (ends at line 363), add:

```python

    # ─── Architecture: canonical import source ─────────────────────────
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
    ),
```

- [ ] **Step 3: Verify no self-violations**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1 | tail -5`

Expected: `No issues found.` (the repo imports `glob_match` from `glob_util` everywhere after Phase 1).

- [ ] **Step 4: Commit**

```bash
git add enforcer_config.py
git commit -s -m "feat(config): add canonical-import-source rule

Uses CanonicalImportMatcher to enforce glob_match/_glob_match imported
from enforcer.glob_util, not from re-exporting modules. Prevents the
Phase 1 regression where matchers imported _glob_match from enforcer.rule."
```

---

## Task 5: Add `config-size-cap` and `no-scratch-files` rules

**Files:**
- Modify: `enforcer_config.py`

- [ ] **Step 1: Add `config-size-cap` rule**

After the `file-max-lines` rule (ends at line 583), add:

```python

    # ─── Config size: warn when approaching complexity limit ───────────
    Rule(
        id="config-size-cap",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=900)],
        file_globs=["enforcer_config.py"],
        diff_only=False,
        message="enforcer_config.py is {matched_value} lines — approaching complexity limit (900).",
        fix_instruction="Split rules into separate config modules or reduce rule count.",
        rationale="A monolithic config file is hard to review and maintain. WARN to allow growth, signal when splitting is needed.",
    ),
```

- [ ] **Step 2: Add `no-scratch-files` rule**

After the `config-size-cap` rule, add:

```python

    # ─── Repo hygiene: no scratch files at root ────────────────────────
    Rule(
        id="no-scratch-files",
        severity=Severity.ERROR,
        matchers=[AlwaysMatcher(matched_value="scratch file at repo root")],
        file_globs=["scratch_*.py"],
        diff_only=False,
        message="Scratch/debug file at repo root: {matched_value}. Delete it.",
        fix_instruction="Delete the file. Use /tmp or a git-ignored directory for scratch work.",
        rationale="Committed scratch files trigger style violations and clutter the repo root.",
    ),
```

- [ ] **Step 3: Verify config is under 900 lines**

Run: `wc -l enforcer_config.py`

Expected: under 900 (currently 826, adding ~24 lines = ~850).

- [ ] **Step 4: Verify no violations**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1 | tail -5`

Expected: `No issues found.` (the WARN rule won't fire until 900+ lines).

- [ ] **Step 5: Commit**

```bash
git add enforcer_config.py
git commit -s -m "feat(config): add config-size-cap WARN and no-scratch-files ERROR

config-size-cap: LineCountMatcher(900) on enforcer_config.py, WARNs when
approaching complexity limit. Phase 3 will split under 400.

no-scratch-files: AlwaysMatcher on scratch_*.py at repo root, ERRORs on
committed debug files. Prevents the scratch_violations.py regression."
```

---

## Task 6: Fix `DocSyncMatcher` hard-coded `rule_id`

**Files:**
- Modify: `enforcer/matchers/doc_sync.py`

- [ ] **Step 1: Remove hard-coded `rule_id`**

In `enforcer/matchers/doc_sync.py`, line 33:

```python
            return [Match(file=file_ctx.path, line=0, rule_id="conventions-md-stale",
```

becomes:

```python
            return [Match(file=file_ctx.path, line=0,
```

The runner stamps `rule_id` from the owning rule (`rule.py:59`), so the hard-coded value is overwritten anyway.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_matchers/test_doc_sync.py --tb=short -q`

Expected: all pass (9 tests).

- [ ] **Step 3: Commit**

```bash
git add enforcer/matchers/doc_sync.py
git commit -s -m "fix(doc-sync): remove hard-coded rule_id from Match

The runner stamps rule_id from the owning rule (rule.py:59), so the
hard-coded value was overwritten anyway. Removing it eliminates confusion
about who owns the rule_id."
```

---

## Task 7: Regenerate CONVENTIONS.md and verify

**Files:**
- Modify: `CONVENTIONS.md`

- [ ] **Step 1: Regenerate docs**

Run: `python -m enforcer.cli sync-doc --config enforcer_config.py`

Expected: `Wrote CONVENTIONS.md` (or no output if already in sync).

- [ ] **Step 2: Verify diff includes 3 new rules**

Run: `git diff --stat CONVENTIONS.md`

Expected: changes (3 new rules added: canonical-import-source, config-size-cap, no-scratch-files).

- [ ] **Step 3: Run full enforcer check**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1`

Expected: `No issues found.`

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`

Expected: all pass (803 + 8 new = 811 tests).

- [ ] **Step 5: Commit**

```bash
git add CONVENTIONS.md
git commit -s -m "docs(conventions): regenerate after adding 3 new Phase 2 rules

canonical-import-source (ERROR), config-size-cap (WARN),
no-scratch-files (ERROR)."
```

---

## Self-Review Notes

**Spec coverage:**
- Section 1 (`CanonicalImportMatcher`): Tasks 1, 2, 3 ✓
- Section 2 (config rules): Tasks 4, 5 ✓
- Section 3 (`DocSyncMatcher` fix): Task 6 ✓
- Verification: Task 7 ✓

**Placeholder scan:** No TBD/TODO. All code blocks complete.

**Type consistency:** `CanonicalImportMatcher` has `canonical: dict[str, str]` field, `needs: Needs = Needs.AST_PY`. Config uses `CanonicalImportMatcher(canonical={...})`. Test file uses `_CANONICAL = {"glob_match": "enforcer.glob_util", ...}`. Consistent.
