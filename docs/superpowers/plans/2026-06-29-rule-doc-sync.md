# Rule Doc Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a natural-language conventions markdown file from configured rules, with a rationale field per rule, a `sync-doc` CLI command, and a self-enforcement matcher that blocks drift.

**Architecture:** One new `Rule.rationale` field. One new `render_rules_doc()` function in `enforcer/docs.py`. One new `DocSyncMatcher` in `enforcer/matchers/doc_sync.py`. One new `sync-doc` CLI subcommand. One-line addition to `_build_shared_ctx` to stash `__rules__`. Backfill all 25 existing rules with rationale. One new `conventions-md-stale` self-enforcement rule.

**Tech Stack:** Python 3.11+, Click (CLI), pytest, dataclasses, stdlib `re`/`pathlib`.

**Spec:** `docs/superpowers/specs/2026-06-29-rule-doc-sync-design.md`

---

### Task 1: Add `rationale` field to `Rule` dataclass

**Files:**
- Modify: `enforcer/rule.py:28-44`
- Test: `tests/test_rule.py` (add case at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rule.py`:

```python
def test_rule_rationale_default_empty():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
    )
    assert rule.rationale == ""


def test_rule_rationale_set():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        rationale="Hex colors break theming.",
    )
    assert rule.rationale == "Hex colors break theming."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rule.py::test_rule_rationale_default_empty tests/test_rule.py::test_rule_rationale_set -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'rationale'`

- [ ] **Step 3: Add the field to `Rule`**

In `enforcer/rule.py`, add `rationale: str = ""` as the last field in the `Rule` dataclass (after `fix: Callable | None = None` at line 44):

```python
    fix: Callable | None = None
    rationale: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rule.py::test_rule_rationale_default_empty tests/test_rule.py::test_rule_rationale_set -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regression**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add enforcer/rule.py tests/test_rule.py
git commit -m "feat(rule): add rationale field to Rule dataclass"
```

---

### Task 2: Implement `render_rules_doc()` prose renderer

**Files:**
- Modify: `enforcer/docs.py` (add function after existing `render_rules_markdown`)
- Test: `tests/test_docs.py` (add cases at end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docs.py`:

```python
import re
from enforcer.docs import render_rules_doc


def test_render_doc_empty_rules():
    md = render_rules_doc([])
    assert "# Conventions" in md
    assert "No rules configured." in md


def test_render_doc_single_rule_with_rationale():
    rules = [
        Rule(
            id="no-print",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"^\s*print\s*\(")],
            file_globs=["enforcer/**/*.py"],
            message="print() found in library code at {file}:{line}.",
            fix_instruction="Replace print() with sys.stderr.write(...).",
            rationale="print() writes to stdout, which is reserved for machine-readable output.",
        ),
    ]
    md = render_rules_doc(rules)
    assert "# Conventions" in md
    assert "## ERROR" in md
    assert "### no-print" in md
    assert "**Why:**" in md
    assert "machine-readable output" in md
    assert "**Applies to:**" in md
    assert "enforcer/**/*.py" in md
    assert "**Fix:**" in md
    assert "sys.stderr.write" in md


def test_render_doc_rule_without_rationale():
    rules = [
        Rule(
            id="no-print",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["enforcer/**/*.py"],
            message="print() found.",
            fix_instruction="Replace print().",
        ),
    ]
    md = render_rules_doc(rules)
    assert "### no-print" in md
    assert "**Why:**" not in md


def test_render_doc_whitespace_only_rationale_omitted():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="msg",
            rationale="   ",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Why:**" not in md


def test_render_doc_callable_message_guard():
    rules = [
        Rule(
            id="dyn",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message=lambda m: f"Dynamic at {m.line}",
        ),
    ]
    md = render_rules_doc(rules)
    assert "(dynamic message)" in md


def test_render_doc_llm_consequence():
    from enforcer import LLMConsequence
    rules = [
        Rule(
            id="llm-rule",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["*.py"],
            llm_consequence=LLMConsequence(
                provider="test", model="gpt-4",
                prompt="Is this function focused?",
            ),
        ),
    ]
    md = render_rules_doc(rules)
    assert "**LLM check:**" in md
    assert "Is this function focused?" in md
    assert "gpt-4" in md


def test_render_doc_diff_only_note():
    rules = [
        Rule(
            id="diff-rule",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="msg",
            diff_only=True,
        ),
    ]
    md = render_rules_doc(rules)
    assert "changed lines only" in md


def test_render_doc_severity_grouping_order():
    rules = [
        Rule(id="z-info", severity=Severity.INFO, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="a-error", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="m-warn", severity=Severity.WARN, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    lines = md.split("\n")
    err_idx = next(i for i, l in enumerate(lines) if "## ERROR" in l)
    warn_idx = next(i for i, l in enumerate(lines) if "## WARN" in l)
    info_idx = next(i for i, l in enumerate(lines) if "## INFO" in l)
    assert err_idx < warn_idx < info_idx


def test_render_doc_sorted_within_group():
    rules = [
        Rule(id="z-rule", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="a-rule", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    lines = md.split("\n")
    a_idx = next(i for i, l in enumerate(lines) if "### a-rule" in l)
    z_idx = next(i for i, l in enumerate(lines) if "### z-rule" in l)
    assert a_idx < z_idx


def test_render_doc_determinism():
    rules = [
        Rule(id="b", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m", rationale="why"),
        Rule(id="a", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m", rationale="why"),
    ]
    md1 = render_rules_doc(rules)
    md2 = render_rules_doc(rules)
    assert md1 == md2


def test_render_doc_placeholder_stripping():
    rules = [
        Rule(
            id="snake",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="Function '{matched_value}' at {file}:{line} must be snake_case",
        ),
    ]
    md = render_rules_doc(rules)
    assert "{matched_value}" not in md
    assert "{file}" not in md
    assert "{line}" not in md
    assert "Function" in md
    assert "snake_case" in md


def test_render_doc_metadata_suffix():
    from enforcer import RuleType
    rules = [
        Rule(
            id="branch-naming",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*"],
            rule_type=RuleType.METADATA,
            message="Branch doesn't match pattern.",
        ),
    ]
    md = render_rules_doc(rules)
    assert "metadata rule, checked once per run" in md


def test_render_doc_excludes_line():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            exclude_globs=["**/test*"],
            message="m",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Excludes:**" in md
    assert "**/test*" in md


def test_render_doc_read_targets_line():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            read_targets=["**/colors.scss"],
            message="m",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Read targets:**" in md
    assert "colors.scss" in md


def test_render_doc_rule_count_in_header():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="b", severity=Severity.WARN, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    assert "2 rules configured" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docs.py -k "render_doc" -v`
Expected: FAIL with `ImportError: cannot import name 'render_rules_doc'`

- [ ] **Step 3: Implement `render_rules_doc`**

Add to `enforcer/docs.py` after the existing `render_rules_markdown` function:

```python
def render_rules_doc(rules: list[Rule], *, workspace: str | None = None) -> str:
    """Render configured rules as natural-language markdown instructions."""
    if not rules:
        return "# Conventions\n\nNo rules configured.\n"

    severity_order = [
        (Severity.ERROR, "ERROR — must fix before commit"),
        (Severity.WARN, "WARN — blocks unless acknowledged"),
        (Severity.INFO, "INFO — advisory"),
    ]

    lines = ["# Conventions", ""]
    lines.append(f"_{len(rules)} rules configured. Auto-generated by `enforcer sync-doc`. Do not edit by hand._")
    lines.append("")

    for sev, heading in severity_order:
        sev_rules = sorted(
            [r for r in rules if r.severity == sev],
            key=lambda r: r.id,
        )
        if not sev_rules:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for rule in sev_rules:
            lines.extend(_render_rule_doc(rule))
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def _render_rule_doc(rule: Rule) -> list[str]:
    """Render a single rule as natural-language markdown lines."""
    out: list[str] []
    out.append(f"### {rule.id}")
    out.append("")

    # Imperative sentence: message with placeholders stripped, callable guard.
    if callable(rule.message):
        msg = "(dynamic message)"
    else:
        msg = rule.message or ""
    msg = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "", msg)
    msg = re.sub(r"  +", " ", msg).strip()
    if msg:
        out.append(msg)
        out.append("")

    # Why block (rationale, if non-empty after strip).
    if rule.rationale.strip():
        out.append(f"**Why:** {rule.rationale.strip()}")
        out.append("")

    # Applies to (globs verbatim + metadata suffix).
    globs_str = ", ".join(rule.file_globs) if rule.file_globs else "(none)"
    from enforcer.types import RuleType
    suffix = " (metadata rule, checked once per run)" if rule.rule_type == RuleType.METADATA else ""
    out.append(f"**Applies to:** {globs_str}{suffix}")
    out.append("")

    # Excludes.
    if rule.exclude_globs:
        out.append(f"**Excludes:** {', '.join(rule.exclude_globs)}")
        out.append("")

    # Fix instruction.
    if rule.fix_instruction.strip():
        out.append(f"**Fix:** {rule.fix_instruction}")
        out.append("")

    # Read targets.
    if rule.read_targets:
        out.append(f"**Read targets:** {', '.join(rule.read_targets)}")
        out.append("")

    # LLM consequence.
    if rule.llm_consequence:
        out.append(f"**LLM check:** {rule.llm_consequence.prompt}")
        out.append(f"**Model:** {rule.llm_consequence.model}")
        out.append("")

    # diff_only note.
    if rule.diff_only:
        out.append("_Checked on changed lines only (`--staged`)._")
        out.append("")

    return out
```

Also add `import re` at the top of `enforcer/docs.py` (after the existing `from __future__ import annotations` line):

```python
from __future__ import annotations
import re
from enforcer.rule import Rule
from enforcer.types import Severity
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docs.py -k "render_doc" -v`
Expected: All PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add enforcer/docs.py tests/test_docs.py
git commit -m "feat(docs): add render_rules_doc prose renderer"
```

---

### Task 3: Add `sync-doc` CLI command + `__rules__` in `shared_ctx`

**Files:**
- Modify: `enforcer/cli.py:156-168` (`_build_shared_ctx`), add new command after `docs` command (line ~292)
- Test: `tests/test_cli.py` (add cases at end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_cli_sync_doc_writes_file(runner, empty_config, tmp_path):
    config_with_rule = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test-rule", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", fix_instruction="Remove it.", rationale="Print is bad.")]
WORKSPACE = "."
'''
    config_file = tmp_path / "enforcer_config.py"
    config_file.write_text(config_with_rule)
    output_file = tmp_path / "OUT.md"
    result = runner.invoke(cli, ["sync-doc", "--config", str(config_file), "-o", str(output_file)])
    assert result.exit_code == 0
    content = output_file.read_text()
    assert "# Conventions" in content
    assert "### test-rule" in content
    assert "**Why:**" in content
    assert "Print is bad." in content


def test_cli_sync_doc_default_output(runner, empty_config, tmp_path):
    import os
    monkeypatch_dir = tmp_path
    config_file = monkeypatch_dir / "enforcer_config.py"
    config_file.write_text('''
from enforcer import Rule, Severity
RULES = []
WORKSPACE = "."
''')
    cwd = os.getcwd()
    os.chdir(str(monkeypatch_dir))
    try:
        result = runner.invoke(cli, ["sync-doc", "--config", str(config_file)])
        assert result.exit_code == 0
        assert (monkeypatch_dir / "CONVENTIONS.md").exists()
    finally:
        os.chdir(cwd)


def test_build_shared_ctx_stashes_rules():
    """_build_shared_ctx must stash __rules__ and __workspace__."""
    from enforcer.cli import _build_shared_ctx
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity

    config = Config(
        rules=[Rule(id="x", severity=Severity.ERROR, matchers=[], file_globs=["*.py"])],
        workspace="/tmp/test",
    )
    builder = FileContextBuilder(workspace="/tmp/test")
    ctx = _build_shared_ctx(config, builder, "/tmp/test")
    assert "__rules__" in ctx
    assert len(ctx["__rules__"]) == 1
    assert ctx["__rules__"][0].id == "x"
    assert "__workspace__" in ctx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::test_cli_sync_doc_writes_file tests/test_cli.py::test_cli_sync_doc_default_output tests/test_cli.py::test_build_shared_ctx_stashes_rules -v`
Expected: FAIL — `sync-doc` command not found, `__rules__` not in shared_ctx.

- [ ] **Step 3: Add `__rules__` and `__workspace__` to `_build_shared_ctx`**

In `enforcer/cli.py`, modify `_build_shared_ctx` (line 156) to add two lines at the top of the function body:

```python
def _build_shared_ctx(config, builder, ws: str) -> dict:
    """Build shared context dict from rule read_targets."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            if target in shared_ctx:
                continue
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                target_ctx = builder.build(rel)
                shared_ctx.setdefault(target, target_ctx)
    return shared_ctx
```

- [ ] **Step 4: Add the `sync-doc` CLI command**

In `enforcer/cli.py`, add after the `docs` command (after line 291, before the `install` command):

```python
@cli.command(name="sync-doc")
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--output", "-o", default="CONVENTIONS.md")
def sync_doc(config_path, output):
    """Regenerate the natural-language conventions doc from configured rules."""
    from enforcer.docs import render_rules_doc

    config = load_config(config_path)
    fresh = render_rules_doc(config.rules, workspace=config.workspace)

    _assert_output_contained(output, config.workspace or ".")
    Path(output).write_text(fresh, encoding="utf-8")
    click.echo(f"Wrote {output}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::test_cli_sync_doc_writes_file tests/test_cli.py::test_cli_sync_doc_default_output tests/test_cli.py::test_build_shared_ctx_stashes_rules -v`
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/cli.py tests/test_cli.py
git commit -m "feat(cli): add sync-doc command, stash __rules__ in shared_ctx"
```

---

### Task 4: Implement `DocSyncMatcher`

**Files:**
- Create: `enforcer/matchers/doc_sync.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_doc_sync.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_matchers/test_doc_sync.py`:

```python
import pytest
from pathlib import Path
from enforcer.types import FileContext, Match
from enforcer import Rule, Severity
from enforcer.matchers.regex import RegexMatcher


def _write_config(tmp_path, rules_src):
    """Write a minimal enforcer_config.py to tmp_path."""
    (tmp_path / "enforcer_config.py").write_text(rules_src)


CONFIG_WITH_RULE = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
WORKSPACE = "."
'''


def test_doc_sync_in_sync(tmp_path, monkeypatch):
    """When CONVENTIONS.md matches a fresh render, no matches."""
    from enforcer.matchers.doc_sync import DocSyncMatcher
    from enforcer.docs import render_rules_doc
    from enforcer.config import load_config

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config = load_config("enforcer_config.py")
    fresh = render_rules_doc(config.rules, workspace=config.workspace)
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": config.rules, "__workspace__": "."})
    assert matches == []


def test_doc_sync_stale(tmp_path, monkeypatch):
    """When CONVENTIONS.md content differs, emits a match."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "CONVENTIONS.md").write_text("# Stale content\n")

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": None})  # force fallback to load_config
    assert len(matches) == 1
    assert "stale" in matches[0].message.lower()


def test_doc_sync_missing_file(tmp_path, monkeypatch):
    """When CONVENTIONS.md doesn't exist, emits a match (treated as stale)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": None})
    assert len(matches) == 1


def test_doc_sync_uses_shared_ctx_rules(tmp_path, monkeypatch):
    """When shared_ctx has __rules__, does not call load_config."""
    from enforcer.matchers.doc_sync import DocSyncMatcher
    from enforcer.docs import render_rules_doc

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config_rules = [Rule(id="test", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
    fresh = render_rules_doc(config_rules, workspace=".")
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")

    # Should use shared_ctx rules, not load_config
    matches = matcher.find(ctx, {"__rules__": config_rules, "__workspace__": "."})
    assert matches == []


def test_doc_sync_load_config_error_propagates(tmp_path, monkeypatch):
    """When load_config raises, error propagates (not swallowed)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    monkeypatch.chdir(tmp_path)
    # No enforcer_config.py exists → load_config will raise
    matcher = DocSyncMatcher(config_path="nonexistent.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")

    with pytest.raises(Exception):
        matcher.find(ctx, {"__rules__": None})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_matchers/test_doc_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'DocSyncMatcher'`

- [ ] **Step 3: Create `DocSyncMatcher`**

Create `enforcer/matchers/doc_sync.py`:

```python
"""DocSyncMatcher: flags if the on-disk generated conventions doc differs from a fresh render."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext, Needs


@dataclass
class DocSyncMatcher:
    """Flags if the on-disk generated doc differs from a fresh render.

    Reads config rules from shared_ctx["__rules__"] (set by the CLI runner),
    falling back to load_config(self.config_path) when called standalone.
    Reads the doc file from self.doc_path on disk.
    """
    config_path: str
    doc_path: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        rules = shared_ctx.get("__rules__")
        workspace = shared_ctx.get("__workspace__", ".")
        if rules is None:
            from enforcer.config import load_config
            config = load_config(self.config_path)
            rules = config.rules
            workspace = config.workspace or "."
        from enforcer.docs import render_rules_doc
        fresh = render_rules_doc(rules, workspace=workspace)
        try:
            on_disk = Path(self.doc_path).read_text(encoding="utf-8") if Path(self.doc_path).exists() else ""
        except OSError:
            on_disk = ""
        if on_disk != fresh:
            return [Match(file=file_ctx.path, line=0, rule_id="conventions-md-stale",
                          message="CONVENTIONS.md is stale or missing.", matched_value=self.doc_path)]
        return []
```

- [ ] **Step 4: Export from `__init__.py`**

In `enforcer/matchers/__init__.py`, add the import and `__all__` entry:

After line 19 (`from enforcer.matchers.llm_check import LLMMatcher`), add:

```python
from enforcer.matchers.doc_sync import DocSyncMatcher
```

In the `__all__` list, after `"LLMMatcher",`, add:

```python
    "DocSyncMatcher",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_doc_sync.py -v`
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/matchers/doc_sync.py enforcer/matchers/__init__.py tests/test_matchers/test_doc_sync.py
git commit -m "feat(matchers): add DocSyncMatcher for conventions doc drift detection"
```

---

### Task 5: Backfill `rationale` on all 25 existing rules + add `conventions-md-stale` rule

**Files:**
- Modify: `enforcer_config.py`

- [ ] **Step 1: Backfill `rationale` on all 25 existing rules**

In `enforcer_config.py`, add a `rationale=` keyword argument to every existing `Rule(...)`. The rationales:

For `branch-naming` (line 46-54), add after `fix_instruction`:

```python
        rationale="Branches encode intent; CI/greps depend on the type/ prefix to route checks and changelogs.",
```

For `commit-message` (line 57-65):

```python
        rationale="Conventional Commits enable automated changelog generation and semantic versioning. Unstructured messages break tooling.",
```

For `matcher-test-paired` (line 68-81):

```python
        rationale="Untested matchers ship false positives/negatives silently. Paired tests catch regressions before they reach users.",
```

For `predicate-test-paired` (line 84-97):

```python
        rationale="Predicates filter matches; untested predicates can silently suppress real violations or let false ones through.",
```

For `combinator-test-paired` (line 100-113):

```python
        rationale="Combinators compose matcher logic; untested combinators can invert or short-circuit the intended logic.",
```

For `core-test-paired` (line 116-129):

```python
        rationale="Core modules (rule, runner, context, config) are load-bearing; untested core changes can break every rule.",
```

For `function-snake-case` (line 132-143):

```python
        rationale="snake_case is the Python convention (PEP 8). Deviating creates inconsistency that makes code harder to scan.",
```

For `class-capwords` (line 146-157):

```python
        rationale="CapWords (PascalCase) is the Python convention for classes (PEP 8). Distinguishes types from functions at a glance.",
```

For `no-print` (line 160-167):

```python
        rationale="print() writes to stdout, which is reserved for machine-readable output in CLI tools. Mixing human prose into stdout breaks piping and scripting. sys.stderr is the correct channel for human-facing diagnostics.",
```

For `no-bare-except` (line 170-177):

```python
        rationale="Bare except catches SystemExit and KeyboardInterrupt, masking intentional exits and making debugging impossible.",
```

For `no-secrets` (line 180-188):

```python
        rationale="Hardcoded secrets ship to the repo and can't be rotated without a commit. Env vars separate config from code and keep secrets out of version control.",
```

For `function-max-lines` (line 191-200):

```python
        rationale="Long functions do too much and are hard to test, read, and review. Splitting forces single-responsibility and improves testability.",
```

For `function-max-params` (line 203-212):

```python
        rationale="More than 5 params signals the function does too much; group into a dataclass to make the boundary explicit and the call site readable.",
```

For `cyclomatic-complexity` (line 215-224):

```python
        rationale="High cyclomatic complexity means too many branches — hard to reason about, test, and maintain. Extract branches into helpers or use early returns.",
```

For `no-wildcard-imports` (line 227-235):

```python
        rationale="Wildcard imports pollute the namespace and hide dependencies. Explicit imports make it clear where symbols come from and avoid name collisions.",
```

For `todo-needs-owner` (line 238-246):

```python
        rationale="TODOs without owners never get done. An owner reference makes responsibility explicit and enables grepping for open work.",
```

For `docstring-public` (line 249-257):

```python
        rationale="Public functions are the API surface. Without docstrings, users (and agents) must read the implementation to understand intent — that's a failure of the contract.",
```

For `readme-max-lines` (line 260-273):

```python
        rationale="A README over 300 lines is too long for a landing doc. Bloat hides the getting-started path; details belong in docs/.",
```

For `commit-msg-aligns-with-changes` (line 276-288):

```python
        rationale="A commit message that doesn't describe the actual changes misleads future archaeologists using git log/blame. The LLM sanity check catches gross mismatches.",
```

For `verify-types-changed` (line 297-305):

```python
        rationale="types.py is load-bearing — every matcher, predicate, and combinator depends on it. Changes here can break the entire rule engine silently.",
```

For `verify-rule-changed` (line 308-316):

```python
        rationale="rule.py contains _glob_match and Rule.check() — every rule flows through it. Changes here affect glob matching and metadata stamping for all rules.",
```

For `verify-runner-changed` (line 319-327):

```python
        rationale="runner.py drives severity filtering, LLM consequence execution, and cross-file finalizers. Changes here can silently change which rules fire.",
```

For `verify-context-changed` (line 330-338):

```python
        rationale="context.py owns the parse-once cache. A broken cache means every AST matcher re-parses or gets stale ASTs.",
```

For `verify-config-changed` (line 341-349):

```python
        rationale="config.py executes enforcer_config.py as a module. Changes here affect how every rule is loaded.",
```

For `verify-parser-changed` (line 352-360):

```python
        rationale="The tree-sitter parser feeds all AST matchers. Changes here can silently break AST detection for Python, TS, or CSS.",
```

- [ ] **Step 2: Add the `conventions-md-stale` self-enforcement rule**

In `enforcer_config.py`, add `DocSyncMatcher` to the imports. In the `from enforcer.matchers import (...)` block (line 24-36), add:

```python
    DocSyncMatcher,
```

Then, at the end of the `RULES` list (before the closing `]` at line 361), add a new rule:

```python

    # ─── Self-enforcement: CONVENTIONS.md in sync ────────────────────────
    Rule(
        id="conventions-md-stale",
        severity=Severity.ERROR,
        matchers=[DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")],
        file_globs=["enforcer_config.py", "CONVENTIONS.md"],
        message="CONVENTIONS.md is stale or missing. Regenerate after changing rules.",
        fix_instruction="Run: enforcer sync-doc",
        rationale="A stale conventions doc misleads agents — they follow rules that no longer match the actual config. The doc must be regenerated whenever RULES changes, and direct edits to CONVENTIONS.md must not drift it from the config.",
    ),
```

- [ ] **Step 3: Verify config loads**

Run: `python -c "from enforcer.config import load_config; c = load_config('enforcer_config.py'); print(f'{len(c.rules)} rules loaded')"`
Expected: `26 rules loaded`

- [ ] **Step 4: Generate initial CONVENTIONS.md**

Run: `python -m enforcer.cli sync-doc`
Expected: `Wrote CONVENTIONS.md`

- [ ] **Step 5: Verify CONVENTIONS.md content**

Run: `head -20 CONVENTIONS.md`
Expected: Header with "26 rules configured", ERROR section, first rule heading.

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer_config.py CONVENTIONS.md
git commit -m "feat(config): backfill rationale on all rules, add conventions-md-stale rule"
```

---

### Task 6: Add pointer line to `AGENTS.md` + document `sync-doc` in `README.md`

**Files:**
- Modify: `AGENTS.md` (add pointer line after title)
- Modify: `README.md` (add `sync-doc` section after `docs` section)

- [ ] **Step 1: Add pointer line to `AGENTS.md`**

In `AGENTS.md`, after line 3 (the description paragraph), add:

```markdown

> Auto-generated rule list: see `CONVENTIONS.md` (run `enforcer sync-doc` to regenerate).
```

- [ ] **Step 2: Add `sync-doc` section to `README.md`**

In `README.md`, after the `enforcer docs` section (after line 82), add:

```markdown
### `enforcer sync-doc`

Generate the natural-language conventions markdown from configured rules. Includes rationale for each rule.

| Flag | Description |
|------|-------------|
| `--output FILE` (`-o`) | Write to file (default: `CONVENTIONS.md`). |

```bash
enforcer sync-doc
enforcer sync-doc -o CONVENTIONS.md
```
```

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 4: Verify pre-commit hook passes**

Run: `python -m enforcer.cli check --staged --no-llm`
Expected: No errors (or only the commit-msg LLM WARN which is expected).

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md
git commit -m "docs: add CONVENTIONS.md pointer to AGENTS.md, document sync-doc in README"
```

---

## Self-Review Notes

**Spec coverage check:**
- `Rule.rationale` field → Task 1 ✓
- `render_rules_doc()` in `enforcer/docs.py` → Task 2 ✓
- `sync-doc` CLI command → Task 3 ✓
- `shared_ctx["__rules__"]` plumbing → Task 3 ✓
- `DocSyncMatcher` + `__init__.py` export → Task 4 ✓
- Backfill 25 rules with rationale → Task 5 ✓
- `conventions-md-stale` self-enforcement rule → Task 5 ✓
- `AGENTS.md` pointer line → Task 6 ✓
- `README.md` sync-doc docs → Task 6 ✓
- Initial `CONVENTIONS.md` generation → Task 5 Step 4 ✓
- Callable message guard → Task 2 test `test_render_doc_callable_message_guard` ✓
- Whitespace-only rationale `.strip()` → Task 2 test `test_render_doc_whitespace_only_rationale_omitted` ✓
- Bidirectional drift (`file_globs` includes `CONVENTIONS.md`) → Task 5 ✓
- `load_config` errors propagate → Task 4 test `test_doc_sync_load_config_error_propagates` ✓
- No `--check` flag (dropped per review) → not in plan ✓
- No `rule-needs-rationale` rule (dropped per review) → not in plan ✓
- No `enforcer/rule_doc.py` module (merged into `docs.py`) → not in plan ✓

**Placeholder scan:** No TBD/TODO. All code blocks are complete.

**Type consistency:** `DocSyncMatcher(config_path=..., doc_path=...)` used consistently in Task 4, Task 5. `render_rules_doc(rules, *, workspace=...)` consistent in Task 2, 3, 4. `__rules__` / `__workspace__` keys consistent in Task 3, 4.
