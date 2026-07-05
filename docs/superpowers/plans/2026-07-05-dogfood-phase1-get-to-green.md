# Dogfood Phase 1: Get to Green — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `enforcer check --all --config enforcer_config.py` pass clean on this repo (zero violations) by resolving all 10 `arch-layer-deps` violations the enforcer flags on itself.

**Architecture:** Approach A (direct fix, no dependency injection). Point glob imports at the canonical low-level module (`glob_util`), reclassify `llm.py` as unclassified infrastructure, move the `render_rules_doc` call from the matcher into the runner via `shared_ctx["__rendered_doc__"]`, add two missing `allowed_edges`, and delete committed debug scratch.

**Tech Stack:** Python 3.11+, pytest, Click, tree-sitter. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-05-dogfood-phase1-get-to-green-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `enforcer/matchers/paired_file.py` | PairedFileMatcher | Modify: glob import |
| `enforcer/matchers/allowlist.py` | AllowlistMatcher | Modify: glob import (2 sites) |
| `enforcer/matchers/keyset_sync.py` | KeySetSyncMatcher | Modify: glob import |
| `enforcer/context.py` | FileContextBuilder | Modify: glob import |
| `enforcer/runner.py` | RuleRunner | Modify: split glob import from rule import |
| `enforcer/matchers/llm_check.py` | LLMMatcher | No change (resolved by reclassify) |
| `enforcer/matchers/doc_sync.py` | DocSyncMatcher | Modify: remove fallback, read `__rendered_doc__` |
| `enforcer/check_runner.py` | build_shared_ctx | Modify: pre-render doc into `shared_ctx` |
| `enforcer_config.py` | Self-enforcement config | Modify: reclassify llm, add edges, update DocSyncMatcher construction |
| `tests/test_glob_doublestar.py` | Glob tests | Modify: import path |
| `tests/test_matchers/test_doc_sync.py` | DocSyncMatcher tests | Modify: 4 tests updated, 1 removed |
| `scratch_violations.py` | Debug cruft | Delete |

---

## Task 1: Fix glob imports in matchers and context

**Files:**
- Modify: `enforcer/matchers/paired_file.py`
- Modify: `enforcer/matchers/allowlist.py`
- Modify: `enforcer/matchers/keyset_sync.py`
- Modify: `enforcer/context.py`

Each of these files lazy-imports `_glob_match` from `enforcer.rule` (a mid-layer module) inside a function body. The import graph walker sees through lazy imports (it walks the AST), so these trip `arch-layer-deps` (matchers→rule, core→rule). `glob_match` already lives in `enforcer/glob_util.py`, which is unclassified — importing from it is never a violation.

- [ ] **Step 1: Fix `paired_file.py`**

In `enforcer/matchers/paired_file.py`:

Add top-level import after line 7 (`from enforcer.types import Match, FileContext, Needs`):

```python
from enforcer.glob_util import glob_match
```

Remove the lazy import at line 41 and rename the call site. The block:

```python
        # ponytail: skip if the source path doesn't match the source_glob
        from enforcer.rule import _glob_match
        if not _glob_match(path, self.source_glob):
            return []
```

becomes:

```python
        # ponytail: skip if the source path doesn't match the source_glob
        if not glob_match(path, self.source_glob):
            return []
```

- [ ] **Step 2: Fix `allowlist.py`**

In `enforcer/matchers/allowlist.py`:

Add top-level import after line 6 (`from enforcer.types import Match, FileContext, Needs`):

```python
from enforcer.glob_util import glob_match
```

Remove the lazy import at line 24 inside `find()`. The block:

```python
    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file content entries not present in the allowlist. Returns list of Match."""
        from enforcer.rule import _glob_match
        shared_ctx = shared_ctx or {}
```

becomes:

```python
    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file content entries not present in the allowlist. Returns list of Match."""
        shared_ctx = shared_ctx or {}
```

Remove the lazy import at line 41 inside `_resolve_targets()` and rename the call site. The block:

```python
    def _resolve_targets(self, shared_ctx: dict) -> list[FileContext]:
        """Resolve target FileContexts by exact key or glob match."""
        from enforcer.rule import _glob_match
        if self.read_target in shared_ctx:
            return [shared_ctx[self.read_target]]
        return [
            ctx for key, ctx in shared_ctx.items()
            if _glob_match(key, self.read_target)
        ]
```

becomes:

```python
    def _resolve_targets(self, shared_ctx: dict) -> list[FileContext]:
        """Resolve target FileContexts by exact key or glob match."""
        if self.read_target in shared_ctx:
            return [shared_ctx[self.read_target]]
        return [
            ctx for key, ctx in shared_ctx.items()
            if glob_match(key, self.read_target)
        ]
```

- [ ] **Step 3: Fix `keyset_sync.py`**

In `enforcer/matchers/keyset_sync.py`:

Add top-level import after line 5 (`from enforcer.types import Match, FileContext, Needs`):

```python
from enforcer.glob_util import glob_match
```

Remove the lazy import at line 57 and rename the call site. The block:

```python
    def _matching_targets(self, glob, shared_ctx, source_path):
        """Yield (path, ctx) pairs from shared_ctx matching the glob, skipping __-prefixed keys and the source file itself."""
        from enforcer.rule import _glob_match
        for key, ctx in shared_ctx.items():
            if key.startswith("__"):
                continue
            if key == source_path:
                continue
            if _glob_match(key, glob):
                yield key, ctx
```

becomes:

```python
    def _matching_targets(self, glob, shared_ctx, source_path):
        """Yield (path, ctx) pairs from shared_ctx matching the glob, skipping __-prefixed keys and the source file itself."""
        for key, ctx in shared_ctx.items():
            if key.startswith("__"):
                continue
            if key == source_path:
                continue
            if glob_match(key, glob):
                yield key, ctx
```

- [ ] **Step 4: Fix `context.py`**

In `enforcer/context.py`:

Add top-level import after line 7 (`from enforcer.parsers.tree_sitter import parse as ts_parse`):

```python
from enforcer.glob_util import glob_match as _glob_match
```

Remove the lazy import at line 79. The block:

```python
    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate all Needs from rules whose file_globs match this path."""
        from enforcer.rule import _glob_match
        needs: set[Needs] = set()
```

becomes:

```python
    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate all Needs from rules whose file_globs match this path."""
        needs: set[Needs] = set()
```

(Call sites at lines 82 and 84 use `_glob_match` — keep the alias to avoid touching them.)

- [ ] **Step 5: Run tests to verify no regressions**

Run: `pytest tests/test_matchers/test_paired_file.py tests/test_matchers/test_allowlist.py tests/test_matchers/test_keyset_sync.py tests/test_context.py tests/test_parse_once.py --tb=short -q`

Expected: all pass (import path changed, behavior unchanged).

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/paired_file.py enforcer/matchers/allowlist.py enforcer/matchers/keyset_sync.py enforcer/context.py
git commit -s -m "refactor(matchers): import glob_match directly from glob_util

Kill lazy `from enforcer.rule import _glob_match` inside function bodies.
The import graph walker sees through lazy imports (AST walk), so these
tripped arch-layer-deps (matchers->rule, core->rule). glob_util is
unclassified, so importing from it is never a violation."
```

---

## Task 2: Fix glob import in runner.py

**Files:**
- Modify: `enforcer/runner.py`

`runner.py` imports `Rule` and `_glob_match` from `enforcer.rule` in one statement. Split it so `_glob_match` comes from `glob_util` directly.

- [ ] **Step 1: Split the import**

In `enforcer/runner.py`, line 5:

```python
from enforcer.rule import Rule, _glob_match
```

becomes:

```python
from enforcer.rule import Rule
from enforcer.glob_util import glob_match as _glob_match
```

All call sites (lines 92, 94, 150, 152) use `_glob_match` — keep the alias to avoid touching them.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_runner.py tests/test_runner_finalizers.py tests/test_metadata_rules.py --tb=short -q`

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add enforcer/runner.py
git commit -s -m "refactor(runner): import glob_match from glob_util, not rule

runner.py (core layer) imported _glob_match from rule.py (mid layer),
tripping arch-layer-deps (core->rule). Import directly from glob_util
(unclassified)."
```

---

## Task 3: Fix glob import in test_glob_doublestar.py

**Files:**
- Modify: `tests/test_glob_doublestar.py`

Test imports `_glob_match` from `enforcer.rule` — should import from `glob_util`.

- [ ] **Step 1: Fix the import**

In `tests/test_glob_doublestar.py`, line 3:

```python
from enforcer.rule import _glob_match
```

becomes:

```python
from enforcer.glob_util import glob_match as _glob_match
```

All call sites use `_glob_match` — keep the alias.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_glob_doublestar.py --tb=short -q`

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_glob_doublestar.py
git commit -s -m "test(glob): import glob_match from glob_util, not rule"
```

---

## Task 4: Reclassify llm.py as unclassified

**Files:**
- Modify: `enforcer_config.py`

`enforcer/llm.py` is in the `io` layer, but it's shared infrastructure (httpx calls, pure helpers). Both `runner.py` (core) and `llm_check.py` (matchers) import from it, tripping `core->io` and `matchers->io`. Reclassify it as unclassified (like `glob_util`, `import_graph`) by removing it from the `io` layer globs.

- [ ] **Step 1: Remove `enforcer/llm.py` from the `io` layer**

In `enforcer_config.py`, the `arch-layer-deps` rule's `layers` dict (around line 313-316):

```python
                "io":         ["enforcer/cli.py", "enforcer/mcp_server.py",
                               "enforcer/reporter.py", "enforcer/docs.py",
                               "enforcer/explain.py", "enforcer/fix.py",
                               "enforcer/ignore.py", "enforcer/llm.py"],
```

becomes:

```python
                "io":         ["enforcer/cli.py", "enforcer/mcp_server.py",
                               "enforcer/reporter.py", "enforcer/docs.py",
                               "enforcer/explain.py", "enforcer/fix.py",
                               "enforcer/ignore.py"],
```

- [ ] **Step 2: Verify violations dropped**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1 | grep "llm_check\|runner.py.*llm" || echo "llm violations resolved"`

Expected: `llm violations resolved` (no matches).

- [ ] **Step 3: Commit**

```bash
git add enforcer_config.py
git commit -s -m "refactor(config): reclassify llm.py as unclassified infra

llm.py is shared infrastructure (httpx calls, pure helpers), not
user-facing I/O. Both runner.py (core) and llm_check.py (matchers)
import from it, tripping core->io and matchers->io. Reclassify as
unclassified (like glob_util, import_graph)."
```

---

## Task 5: Add missing allowed_edges (rule→types, rule→combinators)

**Files:**
- Modify: `enforcer_config.py`

`rule.py` imports from `types` and `combinators.core`. Both are below `rule` in the layer model (rule composes combinators; both depend on types). The edges are missing from `allowed_edges`.

- [ ] **Step 1: Add the edges**

In `enforcer_config.py`, the `arch-layer-deps` rule's `allowed_edges` list (around line 318-339). Add two entries. After `("combinators", "matchers"),` (line 323), add:

```python
                ("rule", "types"),
                ("rule", "combinators"),
```

Place them in alphabetical-ish order near the existing entries — exact position doesn't matter, just that they're in the list.

- [ ] **Step 2: Verify violations dropped**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1 | grep "rule.py" || echo "rule.py violations resolved"`

Expected: `rule.py violations resolved` (no matches).

- [ ] **Step 3: Commit**

```bash
git add enforcer_config.py
git commit -s -m "refactor(config): add rule->types, rule->combinators edges

rule.py composes combinators (AllOf) and depends on types (Severity,
Match, etc.). Both are lower in the layer model. Adding the edges
reflects the intended dependency direction."
```

---

## Task 6: Remove DocSyncMatcher standalone fallback

**Files:**
- Modify: `enforcer/matchers/doc_sync.py`
- Modify: `enforcer/check_runner.py`
- Modify: `enforcer_config.py`

`DocSyncMatcher.find()` lazy-imports `load_config` (core) and `render_rules_doc` (io) as a fallback when `shared_ctx["__rules__"]` is absent. The runner always populates `__rules__`. The lazy imports trip `matchers→core` and `matchers→io`.

Fix: the runner pre-renders the doc and stashes it in `shared_ctx["__rendered_doc__"]`. The matcher becomes pure: read on-disk `doc_path`, compare to `shared_ctx["__rendered_doc__"]`. No imports from `io` or `core`.

- [ ] **Step 1: Rewrite `DocSyncMatcher`**

Replace the entire contents of `enforcer/matchers/doc_sync.py` with:

```python
"""DocSyncMatcher: flags if the on-disk generated conventions doc differs from a fresh render."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext, Needs


@dataclass
class DocSyncMatcher:
    """Flags if the on-disk generated doc differs from a fresh render.

    Reads the freshly rendered doc from shared_ctx["__rendered_doc__"]
    (populated by the runner via render_rules_doc). Reads the on-disk doc
    from self.doc_path. No imports from io or core layers — the matcher
    is pure: read file, compare to string.

    What:       flags when the on-disk doc at `doc_path` differs from `shared_ctx["__rendered_doc__"]`
    Ignores:    matching renders (no diff); unreadable/missing doc files (treated as empty, will flag if render is non-empty)
    Basis:      RAW (compares on-disk file text to shared_ctx string)
    shared_ctx: reads `__rendered_doc__`
    """
    doc_path: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        fresh = shared_ctx.get("__rendered_doc__", "")
        try:
            on_disk = Path(self.doc_path).read_text(encoding="utf-8") if Path(self.doc_path).exists() else ""
        except OSError:
            on_disk = ""
        if on_disk != fresh:
            return [Match(file=file_ctx.path, line=0, rule_id="conventions-md-stale",
                          message="CONVENTIONS.md is stale or missing.", matched_value=self.doc_path)]
        return []
```

Key changes:
- Removed `config_path` field.
- Removed the `if rules is None:` block (lazy imports of `load_config` + `render_rules_doc`).
- Reads `shared_ctx["__rendered_doc__"]` instead of calling `render_rules_doc`.

- [ ] **Step 2: Pre-render doc in `build_shared_ctx`**

In `enforcer/check_runner.py`, function `build_shared_ctx` (around line 159-175). After line 163 (`shared_ctx["__workspace__"] = config.workspace or ws`), add:

```python
    from enforcer.docs import render_rules_doc
    shared_ctx["__rendered_doc__"] = render_rules_doc(config.rules, workspace=config.workspace or ws)
```

The full function becomes:

```python
def build_shared_ctx(config, builder, ws: str, staged_files: list[str] | None = None) -> dict:
    """Build shared context dict from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    from enforcer.docs import render_rules_doc
    shared_ctx["__rendered_doc__"] = render_rules_doc(config.rules, workspace=config.workspace or ws)
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:
                    shared_ctx[rel] = builder.build(rel)
    if staged_files and _has_architecture_matcher(config.rules):
        from enforcer.import_graph import ImportGraphBuilder
        graph_builder = ImportGraphBuilder(builder=builder, workspace=ws)
        shared_ctx["__import_graph__"] = graph_builder.build(staged_files)
    return shared_ctx
```

Note: `check_runner.py` is in the `core` layer. It imports `enforcer.docs` (io) — this is a new `core->io` import. Check whether `check_runner.py` is already classified as `core` in the arch rule (line 306: `"core": ["enforcer/runner.py", "enforcer/context.py", "enforcer/config.py", "enforcer/check_runner.py"]`). Yes, it's `core`. And `docs.py` is `io`. So `check_runner.py -> docs.py` would be a new `core->io` violation.

**Mitigation:** `check_runner.py` already does `from enforcer.import_graph import ImportGraphBuilder` (line 172) — that's fine because `import_graph.py` is unclassified. But `docs.py` is `io`. We need to either:
- (a) Move `render_rules_doc` to a lower layer (bigger refactor, out of scope).
- (b) Reclassify `docs.py` as unclassified (but it has `_render_matcher_doc_line` which lazy-imports `enforcer.explain` — io).
- (c) Pre-render in the CLI/MCP entrypoint (io layer), not in `check_runner.py`.

Option (c) is cleanest: the caller (cli.py or mcp_server.py) pre-renders and passes the string into `build_shared_ctx`. But that changes `build_shared_ctx`'s signature.

**Revised Step 2:** Have `build_shared_ctx` accept an optional `rendered_doc` parameter. The CLI/MCP callers (io layer) call `render_rules_doc` and pass it in. If not passed, `__rendered_doc__` defaults to empty string (matcher will flag stale — safe default).

In `enforcer/check_runner.py`, function `build_shared_ctx`:

```python
def build_shared_ctx(config, builder, ws: str, staged_files: list[str] | None = None,
                     rendered_doc: str | None = None) -> dict:
    """Build shared context dict from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    shared_ctx["__rendered_doc__"] = rendered_doc or ""
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:
                    shared_ctx[rel] = builder.build(rel)
    if staged_files and _has_architecture_matcher(config.rules):
        from enforcer.import_graph import ImportGraphBuilder
        graph_builder = ImportGraphBuilder(builder=builder, workspace=ws)
        shared_ctx["__import_graph__"] = graph_builder.build(staged_files)
    return shared_ctx
```

- [ ] **Step 3: Update CLI caller to pre-render**

Three call sites (verified):
- `enforcer/cli.py:88` — `shared_ctx = _build_shared_ctx(config, builder, ws, staged_files=file_list)`
- `enforcer/mcp_server.py:40` — `shared_ctx = _build_shared_ctx(config, builder, ws, staged_files=file_list)`
- `enforcer/mcp_server.py:75` — `shared_ctx = _build_shared_ctx(config, builder, ws, staged_files=[path] if path else None)`

At each call site, add before the call:

```python
    from enforcer.docs import render_rules_doc
    rendered_doc = render_rules_doc(config.rules, workspace=config.workspace or ws)
```

And add `rendered_doc=rendered_doc` to the `_build_shared_ctx(...)` call. Example for cli.py:88:

```python
    from enforcer.docs import render_rules_doc
    rendered_doc = render_rules_doc(config.rules, workspace=config.workspace or ws)
    shared_ctx = _build_shared_ctx(config, builder, ws, staged_files=file_list, rendered_doc=rendered_doc)
```

Both `cli.py` and `mcp_server.py` are in the `io` layer — importing `render_rules_doc` from `enforcer.docs` (also `io`) is an intra-layer import, not a violation.

- [ ] **Step 4: Update `enforcer_config.py` DocSyncMatcher construction**

In `enforcer_config.py`, line 798:

```python
        matchers=[DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")],
```

becomes:

```python
        matchers=[DocSyncMatcher(doc_path="CONVENTIONS.md")],
```

- [ ] **Step 5: Run tests (expect failures in doc_sync tests)**

Run: `pytest tests/test_matchers/test_doc_sync.py --tb=short -q`

Expected: failures — tests still construct `DocSyncMatcher(config_path=..., doc_path=...)` and pass `{"__rules__": ...}`. These are updated in Task 7.

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/doc_sync.py enforcer/check_runner.py enforcer_config.py enforcer/cli.py enforcer/mcp_server.py
git commit -s -m "refactor(doc-sync): remove standalone fallback, pre-render in runner

DocSyncMatcher lazy-imported load_config (core) and render_rules_doc
(io), tripping matchers->core and matchers->io. Move the render_rules_doc
call to the io-layer callers (cli/mcp), pass the rendered string via
shared_ctx['__rendered_doc__']. Matcher becomes pure: read file, compare
to string. Remove config_path field (only existed for the fallback)."
```

---

## Task 7: Update DocSyncMatcher tests

**Files:**
- Modify: `tests/test_matchers/test_doc_sync.py`

Tests construct `DocSyncMatcher(config_path=..., doc_path=...)` and pass `{"__rules__": ...}`. Update to construct `DocSyncMatcher(doc_path=...)` and pass `{"__rendered_doc__": ...}`. Remove the test that exercises the removed fallback.

- [ ] **Step 1: Rewrite the test file**

Replace the entire contents of `tests/test_matchers/test_doc_sync.py` with:

```python
import pytest
from pathlib import Path
from enforcer.types import FileContext, Match
from enforcer import Rule, Severity
from enforcer.matchers.regex import RegexMatcher


CONFIG_WITH_RULE = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
WORKSPACE = "."
'''


def _write_config(tmp_path, rules_src):
    """Write a minimal enforcer_config.py to tmp_path."""
    (tmp_path / "enforcer_config.py").write_text(rules_src)


def test_doc_sync_in_sync(tmp_path, monkeypatch):
    """When CONVENTIONS.md matches the rendered doc, no matches."""
    from enforcer.matchers.doc_sync import DocSyncMatcher
    from enforcer.docs import render_rules_doc
    from enforcer.config import load_config

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config = load_config("enforcer_config.py")
    fresh = render_rules_doc(config.rules, workspace=config.workspace)
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_doc__": fresh})
    assert matches == []


def test_doc_sync_stale(tmp_path, monkeypatch):
    """When CONVENTIONS.md content differs, emits a match."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "CONVENTIONS.md").write_text("# Stale content\n")

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_doc__": "# Fresh render\n"})
    assert len(matches) == 1
    assert "stale" in matches[0].message.lower()


def test_doc_sync_missing_file(tmp_path, monkeypatch):
    """When CONVENTIONS.md doesn't exist, emits a match (treated as stale)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_doc__": "# Fresh render\n"})
    assert len(matches) == 1


def test_doc_sync_uses_shared_ctx_rendered_doc(tmp_path, monkeypatch):
    """When shared_ctx has __rendered_doc__, compares to it (not re-rendering)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config_rules = [Rule(id="test", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
    fresh = "# Rendered doc\n"
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")

    # Should use shared_ctx __rendered_doc__, not load_config
    matches = matcher.find(ctx, {"__rendered_doc__": fresh})
    assert matches == []


def test_doc_sync_empty_shared_ctx_flags_stale(tmp_path, monkeypatch):
    """When shared_ctx has no __rendered_doc__ (empty default), flags stale if file exists."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "CONVENTIONS.md").write_text("# Some content\n")

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {})
    assert len(matches) == 1
```

Key changes:
- All constructions: `DocSyncMatcher(config_path=..., doc_path=...)` → `DocSyncMatcher(doc_path=...)`.
- `{"__rules__": config.rules}` → `{"__rendered_doc__": fresh}`.
- `test_doc_sync_load_config_error_propagates` removed (fallback is gone).
- New `test_doc_sync_empty_shared_ctx_flags_stale` covers the empty-default behavior.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_matchers/test_doc_sync.py --tb=short -q`

Expected: all pass (5 tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_matchers/test_doc_sync.py
git commit -s -m "test(doc-sync): update tests for __rendered_doc__ shared_ctx key

Remove config_path from constructions, pass rendered doc string via
shared_ctx. Remove test_doc_sync_load_config_error_propagates (fallback
removed). Add test_doc_sync_empty_shared_ctx_flags_stale."
```

---

## Task 8: Delete scratch_violations.py

**Files:**
- Delete: `scratch_violations.py`

Committed debug scratch at repo root. Triggers `no-print` and `class-capwords`. Not referenced anywhere.

- [ ] **Step 1: Verify no references**

Run: `grep -rn "scratch_violations" --include="*.py" .`

Expected: no matches (or only the file itself).

- [ ] **Step 2: Delete the file**

```bash
git rm scratch_violations.py
```

- [ ] **Step 3: Commit**

```bash
git commit -s -m "chore(hygiene): delete scratch_violations.py

Committed debug scratch at repo root. Triggers no-print and
class-capwords. Not referenced anywhere."
```

---

## Task 9: Verify enforcer check --all passes clean

**Files:** None (verification only)

- [ ] **Step 1: Run full enforcer check**

Run: `python -m enforcer.cli check --all --config enforcer_config.py 2>&1`

Expected: `No issues found.` (possibly with an `[enforcer] LLM call failed` stderr line if no LLM is configured — that's fine, it's the commit-msg-aligns WARN rule failing open).

- [ ] **Step 2: Run full test suite**

Run: `pytest --tb=short -q`

Expected: all pass. One fewer test than before (removed `test_doc_sync_load_config_error_propagates`).

- [ ] **Step 3: Verify CONVENTIONS.md is still in sync**

Run: `python -m enforcer.cli sync-doc --config enforcer_config.py 2>&1 && git diff --stat CONVENTIONS.md`

Expected: no changes (or only the rule count line if edges changed).

If CONVENTIONS.md is stale, regenerate:

```bash
python -m enforcer.cli sync-doc --config enforcer_config.py
git add CONVENTIONS.md
git commit -s -m "docs(conventions): regenerate CONVENTIONS.md after arch rule changes"
```

- [ ] **Step 4: Final commit (if any CONVENTIONS.md changes)**

Only if Step 3 produced changes. Otherwise skip.

---

## Self-Review Notes

**Spec coverage:**
- Section 1 (glob imports): Tasks 1, 2, 3 ✓
- Section 2 (reclassify llm.py): Task 4 ✓
- Section 3 (remove DocSyncMatcher fallback): Tasks 6, 7 ✓
- Section 4 (missing edges): Task 5 ✓
- Section 5 (delete scratch): Task 8 ✓
- Verification: Task 9 ✓

**Placeholder scan:** No TBD/TODO. All code blocks are complete.

**Type consistency:** `DocSyncMatcher` loses `config_path` field, gains nothing. `build_shared_ctx` gains `rendered_doc` param. `shared_ctx["__rendered_doc__"]` is the key used in both matcher and runner. Consistent.

**One concern:** Task 6 Step 2 was revised to avoid a new `core->io` violation (check_runner importing docs). The revised approach passes `rendered_doc` as a parameter from the io-layer caller. This means the caller (cli.py/mcp_server.py) must call `render_rules_doc` before `build_shared_ctx`. The plan's Step 3 covers this, but the exact line numbers in cli.py/mcp_server.py are not pinned — the executor must grep for `build_shared_ctx` call sites and update each.
