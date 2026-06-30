# Rule Clarity — `explain` Command + Docstring/Test Conventions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every rule self-explanatory: a human or agent can answer "what does this rule match, what does it ignore, what does a violation look like" without reading matcher source — via structured docstrings, organized tests, and a new `enforcer explain <rule-id>` command.

**Architecture:** No new fields on `Rule`/matchers. Each matcher class gains a four-section docstring (What/Ignores/Basis/shared_ctx). Paired test files document positive/negative cases parameterized with ≥3 examples. New `enforcer/explain.py` reflects over configured rules + matcher docstrings + test files to render an explainer. New `TestCoverageMatcher` enforces the positive/negative parameterized test convention via AST inspection.

**Tech Stack:** Python 3.11, Click (CLI), tree-sitter (AST), pytest (parametrize), dataclasses, stdlib `inspect`

**Spec:** `docs/superpowers/specs/2026-06-30-rule-clarity-explain-command-design.md`

---

## File Structure

```
enforcer/explain.py                          # NEW — reflection: rule/matcher explainer rendering
enforcer/matchers/test_coverage.py            # NEW — TestCoverageMatcher (AST-inspects test files)
enforcer/matchers/__init__.py                 # MODIFY — export TestCoverageMatcher
enforcer/cli.py                               # MODIFY — add `explain` subcommand
enforcer/docs.py                              # MODIFY — add Matchers block to _render_rule_doc
enforcer/mcp_server.py                        # MODIFY — add explain_rule tool
enforcer_config.py                            # MODIFY — add matcher-docstring-structured + matcher-test-positive-negative rules
enforcer/matchers/*.py                        # MODIFY — retrofit 20 matcher docstrings (4-section convention)
tests/test_explain.py                         # NEW — paired tests for explain.py
tests/test_matchers/test_test_coverage.py     # NEW — paired tests for TestCoverageMatcher
tests/test_cli_explain.py                     # NEW — CLI integration tests
tests/test_mcp_server.py                      # MODIFY — add explain_rule MCP tests
tests/test_docs.py                            # MODIFY — add Matchers block tests
```

---

### Task 1: `_parse_docstring_sections` — docstring parser

**Files:**
- Create: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_explain.py`:

```python
"""Tests for explain module: rule/matcher reflection and rendering."""
import pytest
from enforcer.explain import _parse_docstring_sections


class TestParseDocstringSectionsFound:
    """returns all four labeled sections when present."""

    @pytest.mark.parametrize("label", ["What", "Ignores", "Basis", "shared_ctx"])
    def test_section_present(self, label):
        doc = f"""First line summary.

        What:       flags lines matching pattern
        Ignores:    multiline patterns
        Basis:      RAW (regex on raw text)
        shared_ctx: none
        """
        sections = _parse_docstring_sections(doc)
        assert label in sections
        assert sections[label]  # non-empty

    @pytest.mark.parametrize("missing", ["Ignores", "Basis", "shared_ctx"])
    def test_missing_section_omitted(self, missing):
        doc = f"""Summary.

        What: flags lines
        """
        if missing != "What":
            doc = doc  # only What present
        sections = _parse_docstring_sections(doc)
        assert missing not in sections
        assert "What" in sections


class TestParseDocstringSectionsClean:
    """handles edge cases without crashing."""

    @pytest.mark.parametrize("doc", [
        "",                          # empty
        "No sections here.",         # summary only
        "What: only one section",    # single section, no newline
        None,                        # None input
    ])
    def test_no_crash(self, doc):
        sections = _parse_docstring_sections(doc)
        assert isinstance(sections, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.explain'`

- [ ] **Step 3: Write minimal implementation**

Create `enforcer/explain.py`:

```python
"""Explain module: reflects over configured rules and matcher docstrings to render explainers."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SECTION_RE = re.compile(r'^\s*(What|Ignores|Basis|shared_ctx)\s*:\s*(.+)$', re.MULTILINE)


def _parse_docstring_sections(doc: str | None) -> dict[str, str]:
    """Parse a matcher class docstring into labeled sections (What/Ignores/Basis/shared_ctx).

    Returns dict mapping section label -> text. Missing sections omitted.
    """
    if not doc:
        return {}
    return {m.group(1): m.group(2).strip() for m in _SECTION_RE.finditer(doc)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add docstring section parser for matcher reflection"
```

---

### Task 2: `MatcherExplainer` dataclass + `render_matcher_explainer`

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
import inspect
from dataclasses import is_dataclass
from enforcer.matchers import RegexMatcher
from enforcer.explain import MatcherExplainer, render_matcher_explainer


class TestRenderMatcherExplainerFound:
    """renders class name, docstring sections, and configured params for a matcher."""

    @pytest.mark.parametrize("pattern,redact", [
        (r"^\s*print\s*\(", False),
        (r"password\s*=", True),
        (r"TODO", False),
    ])
    def test_renders_class_name_and_pattern(self, pattern, redact):
        matcher = RegexMatcher(pattern=pattern, redact=redact)
        explainer = render_matcher_explainer(matcher)
        assert explainer.class_name == "RegexMatcher"
        assert explainer.configured_params["pattern"] == pattern
        assert explainer.configured_params["redact"] == redact

    def test_renders_docstring_sections(self):
        matcher = RegexMatcher(pattern=r"print")
        explainer = render_matcher_explainer(matcher)
        # RegexMatcher will have its docstring retrofitted in Task 9;
        # until then the explainer should still return a dict (possibly empty)
        assert isinstance(explainer.docstring_sections, dict)

    def test_explainer_is_dataclass(self):
        assert is_dataclass(MatcherExplainer)


class TestRenderMatcherExplainerClean:
    """handles matchers with minimal or missing docstrings gracefully."""

    @pytest.mark.parametrize("matcher_factory", [
        lambda: RegexMatcher(pattern="x"),
    ])
    def test_no_crash_on_minimal_docstring(self, matcher_factory):
        explainer = render_matcher_explainer(matcher_factory())
        assert explainer.class_name  # always has a name
        assert isinstance(explainer.docstring_sections, dict)
        assert isinstance(explainer.configured_params, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestRenderMatcherExplainerFound -v`
Expected: FAIL with `ImportError: cannot import name 'MatcherExplainer'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py` (after `_parse_docstring_sections`):

```python
import dataclasses


@dataclass
class MatcherExplainer:
    """Reflected metadata for a single matcher instance, rendered by explain."""
    class_name: str
    docstring_sections: dict[str, str]
    configured_params: dict[str, Any]


def render_matcher_explainer(matcher) -> MatcherExplainer:
    """Reflect over a matcher instance: class name, docstring sections, configured (non-default) params."""
    cls = type(matcher)
    doc = inspect.getdoc(matcher)
    sections = _parse_docstring_sections(doc)

    configured: dict[str, Any] = {}
    if dataclasses.is_dataclass(matcher):
        for f in dataclasses.fields(matcher):
            value = getattr(matcher, f.name)
            default = f.default
            # ponytail: include param if it differs from default, or has no default (factory)
            if default is dataclasses.MISSING:
                if f.default_factory is dataclasses.MISSING:  # no default at all — always include
                    configured[f.name] = value
                else:
                    configured[f.name] = value  # factory default — include (can't cheaply compare)
            elif value != default:
                configured[f.name] = value

    return MatcherExplainer(
        class_name=cls.__name__,
        docstring_sections=sections,
        configured_params=configured,
    )
```

Also add `import inspect` at top of file.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add MatcherExplainer + render_matcher_explainer"
```

---

### Task 3: `_find_paired_test` — locate paired test file

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
from pathlib import Path
from enforcer.explain import _find_paired_test


class TestFindPairedTestFound:
    """locates the paired test file for a matcher class."""

    @pytest.mark.parametrize("class_name,expected_file", [
        ("RegexMatcher", "test_regex_matcher.py"),     # preferred long form
        ("ImportMatcher", "test_import_matcher.py"),
        ("DocstringMatcher", "test_docstring.py"),     # falls back to existing short form
    ])
    def test_finds_test_file(self, class_name, expected_file):
        workspace = str(Path(__file__).resolve().parent.parent)  # repo root
        result = _find_paired_test(class_name, workspace)
        assert result is not None
        assert result.name in (expected_file, expected_file.replace("_matcher", ""))


class TestFindPairedTestClean:
    """returns None when no paired test file exists."""

    @pytest.mark.parametrize("class_name", [
        "NonexistentMatcher",       # no such matcher
        "TotallyFake",              # garbage
        "",                         # empty
    ])
    def test_returns_none_when_missing(self, class_name):
        result = _find_paired_test(class_name, str(Path(__file__).resolve().parent.parent))
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestFindPairedTestFound -v`
Expected: FAIL with `ImportError: cannot import name '_find_paired_test'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py`:

```python
import re as _re


def _snake_case_class(class_name: str) -> str:
    """Convert CamelCase class name to snake_case: RegexMatcher -> regex_matcher."""
    s1 = _re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', class_name)
    return _re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _find_paired_test(class_name: str, workspace: str) -> Path | None:
    """Locate the paired test file for a matcher class.

    Tries (in order): tests/test_matchers/test_{snake}.py, tests/test_matchers/test_{snake_without_matcher}.py,
    tests/test_matchers/test_{snake_without_matcher_suffix}.py.
    Returns Path of first existing match, or None.
    """
    snake = _snake_case_class(class_name)
    candidates = [
        f"tests/test_matchers/test_{snake}.py",
        f"tests/test_matchers/test_{snake.replace('_matcher', '')}.py",
    ]
    for rel in candidates:
        p = Path(workspace) / rel
        if p.exists():
            return p
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add _find_paired_test for matcher test discovery"
```

---

### Task 4: `_extract_worked_example` — render a test snippet

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
from enforcer.explain import _extract_worked_example, WorkedExample


class TestExtractWorkedExampleFound:
    """extracts a 4-line worked example from a paired test file."""

    @pytest.mark.parametrize("matcher_class", [
        "RegexMatcher",
        "ImportMatcher",
    ])
    def test_returns_example_for_real_test_file(self, matcher_class):
        workspace = str(Path(__file__).resolve().parent.parent)
        test_path = _find_paired_test(matcher_class, workspace)
        assert test_path is not None
        example = _extract_worked_example(test_path, matcher_class)
        assert example is not None
        assert example.test_class_name  # non-empty
        assert example.test_method_name  # non-empty
        assert example.snippet  # non-empty source lines

    def test_worked_example_is_dataclass(self):
        assert is_dataclass(WorkedExample)


class TestExtractWorkedExampleClean:
    """returns None when test file can't be parsed or has no test classes."""

    @pytest.mark.parametrize("content", [
        "",                              # empty file
        "no tests here",                 # no test class
        "# just a comment",              # no test class
    ])
    def test_returns_none_on_no_tests(self, content, tmp_path):
        test_file = tmp_path / "test_fake.py"
        test_file.write_text(content)
        result = _extract_worked_example(test_file, "FakeMatcher")
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestExtractWorkedExampleFound -v`
Expected: FAIL with `ImportError: cannot import name '_extract_worked_example'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py`:

```python
@dataclass
class WorkedExample:
    """A 4-line snippet from a paired test file, showing input -> match assertion."""
    test_class_name: str
    test_method_name: str
    snippet: str
    file_path: str
    line: int


def _extract_worked_example(test_path: Path, matcher_class_name: str) -> WorkedExample | None:
    """Parse a test file via tree-sitter, return the first test class + method snippet.

    Returns None if the file can't be parsed or has no test classes.
    """
    try:
        source = test_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not source.strip():
        return None

    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    from enforcer.parsers.ast_utils import walk_ast, node_text

    tree = parse(source, Needs.AST_PY)
    if tree is None:
        return None

    root = tree.root_node
    for node in walk_ast(root):
        if node.type == "class_definition":
            class_name = ""
            for child in node.children:
                if child.type == "identifier":
                    class_name = node_text(child)
                    break
            if not class_name.startswith("Test"):
                continue
            # find first method (function_definition) inside this class
            for inner in walk_ast(node):
                if inner.type == "function_definition" and inner.start_point[0] > node.start_point[0] and inner.end_point[0] <= node.end_point[0]:
                    method_name = ""
                    for child in inner.children:
                        if child.type == "identifier":
                            method_name = node_text(child)
                            break
                    # snippet: the method body, first 4 lines
                    start_line = inner.start_point[0]
                    end_line = min(inner.end_point[0] + 1, start_line + 5)
                    lines = source.splitlines()[start_line:end_line]
                    snippet = "\n".join(lines)
                    return WorkedExample(
                        test_class_name=class_name,
                        test_method_name=method_name,
                        snippet=snippet,
                        file_path=str(test_path),
                        line=start_line + 1,
                    )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add _extract_worked_example via tree-sitter test file parse"
```

---

### Task 5: `render_rule_explainer` — text rendering

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
from enforcer.explain import render_rule_explainer


def _sample_rule() -> Rule:
    return Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found in library code at {file}:{line}.",
        fix_instruction="Replace print() with sys.stderr.write(...).",
        rationale="print() writes to stdout.",
        diff_only=True,
    )


class TestRenderRuleExplainerFound:
    """renders the full rule explainer text for a real rule."""

    @pytest.mark.parametrize("field", [
        "Rule: no-print",
        "Severity: ERROR",
        "Applies to: enforcer/**/*.py",
        "Matchers (1):",
        "RegexMatcher",
        "What:",
        "Basis:",
        "Worked example",
    ])
    def test_contains_field(self, field):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=str(Path(__file__).resolve().parent.parent))
        assert field in text

    def test_includes_diff_only_note(self):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=".")
        assert "Diff-only" in text or "diff_only" in text.lower() or "changed lines" in text.lower()

    def test_includes_message_and_fix(self):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=".")
        assert "print() found" in text
        assert "sys.stderr.write" in text


class TestRenderRuleExplainerClean:
    """handles rules with empty matchers or missing fields."""

    @pytest.mark.parametrize("matchers", [
        [],  # empty matchers list
    ])
    def test_no_crash_on_empty_matchers(self, matchers):
        rule = Rule(id="empty", severity=Severity.INFO, matchers=matchers, file_globs=["*.py"], message="m")
        text = render_rule_explainer(rule, workspace=".")
        assert "Rule: empty" in text
        assert "Matchers (0):" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestRenderRuleExplainerFound -v`
Expected: FAIL with `ImportError: cannot import name 'render_rule_explainer'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py`:

```python
from enforcer.rule import Rule
from enforcer.types import RuleType


def render_rule_explainer(rule: Rule, workspace: str = ".") -> str:
    """Render a full text explainer for a rule: metadata + matcher details + worked example."""
    lines: list[str] = []
    lines.append(f"Rule: {rule.id}")
    sev_label = rule.severity.value.upper()
    action = "blocks" if rule.severity.value in ("error", "warn") else "advisory"
    lines.append(f"Severity: {sev_label} ({action})")

    globs = ", ".join(rule.file_globs) if rule.file_globs else "(none)"
    suffix = " (metadata rule, checked once per run)" if rule.rule_type == RuleType.METADATA else " (content rule, per-file)"
    lines.append(f"Applies to: {globs}{suffix}")
    if rule.diff_only:
        lines.append("Diff-only: yes (fires only on --staged changed lines)")
    lines.append("")

    if rule.message:
        msg = "(dynamic message)" if callable(rule.message) else rule.message
        lines.append(f"Message: {msg}")
    if rule.fix_instruction:
        lines.append(f"Fix:     {rule.fix_instruction}")
    if rule.rationale:
        lines.append(f"Why:     {rule.rationale}")
    lines.append("")

    matchers = rule.matchers or []
    lines.append(f"Matchers ({len(matchers)}):")
    for i, matcher in enumerate(matchers, 1):
        explainer = render_matcher_explainer(matcher)
        lines.append(f"  {i}. {explainer.class_name}")
        for label in ("What", "Ignores", "Basis", "shared_ctx"):
            if label in explainer.docstring_sections:
                lines.append(f"     {label + ':':12} {explainer.docstring_sections[label]}")
        for param, value in explainer.configured_params.items():
            lines.append(f"     {param}: {value!r}")

        test_path = _find_paired_test(explainer.class_name, workspace)
        if test_path:
            example = _extract_worked_example(test_path, explainer.class_name)
            if example:
                lines.append("")
                lines.append(f"     Worked example ({example.file_path}:{example.test_class_name}.{example.test_method_name}):")
                for snippet_line in example.snippet.splitlines():
                    lines.append(f"         {snippet_line}")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS (the `What:`/`Basis:` assertions pass only after Task 9 retrofits docstrings — for now they may FAIL. **Adjustment:** temporarily relax those two assertions to `assert "RegexMatcher" in text` until Task 9. See Step 4 note below.)

**Step 4 note:** The `What:` and `Basis:` assertions assume the docstring retrofit is done. Since Task 9 retrofits docstrings, these tests will fail until then. Two options:
- (a) Move Task 9 before Task 5 (do the docstring retrofit first).
- (b) Relax those two assertions now, tighten after Task 9.

**Recommendation: (a)** — reorder so the RegexMatcher docstring retrofit (Task 9, first matcher) happens before this test runs. Move Task 9's RegexMatcher portion here. For now, relax to:

```python
    # parametrize: remove "What:" and "Basis:" from the parametrize list; add a TODO comment
    @pytest.mark.parametrize("field", [
        "Rule: no-print",
        "Severity: ERROR",
        "Applies to: enforcer/**/*.py",
        "Matchers (1):",
        "RegexMatcher",
        # "What:",   # re-enable after Task 9 docstring retrofit
        # "Basis:",  # re-enable after Task 9 docstring retrofit
        "Worked example",
    ])
```

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add render_rule_explainer text renderer"
```

---

### Task 6: `render_rule_explainer_json` — JSON rendering

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
import json
from enforcer.explain import render_rule_explainer_json


class TestRenderRuleExplainerJsonFound:
    """returns a JSON-serializable dict with rule metadata and matcher details."""

    @pytest.mark.parametrize("key", [
        "rule_id", "severity", "file_globs", "diff_only", "message",
        "fix_instruction", "rationale", "matchers",
    ])
    def test_has_key(self, key):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        assert key in data

    def test_matchers_list_has_class_name(self):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        assert len(data["matchers"]) == 1
        assert data["matchers"][0]["class_name"] == "RegexMatcher"

    def test_json_serializable(self):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        # must not raise
        json.dumps(data)


class TestRenderRuleExplainerJsonClean:
    """handles rules with no matchers."""

    def test_empty_matchers_list(self):
        rule = Rule(id="empty", severity=Severity.INFO, matchers=[], file_globs=["*.py"], message="m")
        data = render_rule_explainer_json(rule, workspace=".")
        assert data["matchers"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestRenderRuleExplainerJsonFound -v`
Expected: FAIL with `ImportError: cannot import name 'render_rule_explainer_json'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py`:

```python
def render_rule_explainer_json(rule: Rule, workspace: str = ".") -> dict:
    """Render a rule explainer as a JSON-serializable dict."""
    matchers_data = []
    for matcher in rule.matchers or []:
        explainer = render_matcher_explainer(matcher)
        test_path = _find_paired_test(explainer.class_name, workspace)
        example = _extract_worked_example(test_path, explainer.class_name) if test_path else None
        matchers_data.append({
            "class_name": explainer.class_name,
            "docstring_sections": explainer.docstring_sections,
            "configured_params": {k: repr(v) for k, v in explainer.configured_params.items()},
            "paired_test": str(test_path) if test_path else None,
            "worked_example": {
                "test_class": example.test_class_name,
                "test_method": example.test_method_name,
                "snippet": example.snippet,
                "file_path": example.file_path,
                "line": example.line,
            } if example else None,
        })
    return {
        "rule_id": rule.id,
        "severity": rule.severity.value,
        "file_globs": rule.file_globs,
        "diff_only": rule.diff_only,
        "rule_type": rule.rule_type.value,
        "message": "(dynamic)" if callable(rule.message) else rule.message,
        "fix_instruction": rule.fix_instruction,
        "rationale": rule.rationale,
        "matchers": matchers_data,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add render_rule_explainer_json for structured output"
```

---

### Task 7: `load_rule_for_explain` — find rule by id + close matches

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
from enforcer.explain import load_rule_for_explain, ExplainResult


class TestLoadRuleForExplainFound:
    """finds a rule by exact id match."""

    @pytest.mark.parametrize("rule_id,expected_found", [
        ("no-raw-hex", True),
        ("max-lines-readme", True),
        ("nonexistent-rule", False),
    ])
    def test_finds_or_not(self, rule_id, expected_found, tmp_path):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-raw-hex", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")], file_globs=["*.ts"], message="m"),
    Rule(id="max-lines-readme", severity=Severity.WARN, matchers=[], file_globs=["README.md"], message="m"),
]
WORKSPACE = "."
''')
        result = load_rule_for_explain(str(cfg), rule_id)
        assert (result.rule is not None) == expected_found


class TestLoadRuleForExplainClean:
    """suggests close matches when rule id not found."""

    def test_suggests_close_matches(self, tmp_path):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-raw-hex", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")], file_globs=["*.ts"], message="m"),
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        result = load_rule_for_explain(str(cfg), "no-raw-he")
        assert result.rule is None
        assert "no-raw-hex" in result.suggestions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestLoadRuleForExplainFound -v`
Expected: FAIL with `ImportError: cannot import name 'load_rule_for_explain'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/explain.py`:

```python
@dataclass
class ExplainResult:
    """Result of looking up a rule for explain: the rule (or None) + close-match suggestions."""
    rule: Rule | None
    suggestions: list[str] = field(default_factory=list)
    config_workspace: str = "."


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings. Stdlib-only, O(n*m)."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load_rule_for_explain(config_path: str, rule_id: str) -> ExplainResult:
    """Load config, find rule by id. Returns ExplainResult with rule or close-match suggestions."""
    from enforcer.config import load_config
    config = load_config(config_path)
    rule = next((r for r in config.rules if r.id == rule_id), None)
    suggestions: list[str] = []
    if rule is None:
        # ponytail: suggest rules within edit distance 3, sorted by distance
        scored = [(_levenshtein(rule_id, r.id), r.id) for r in config.rules]
        scored.sort()
        suggestions = [s for _, s in scored[:5] if _levenshtein(rule_id, s) <= 5]
    return ExplainResult(rule=rule, suggestions=suggestions, config_workspace=config.workspace or ".")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): add load_rule_for_explain with close-match suggestions"
```

---

### Task 8: Combinator recursion in `render_matcher_explainer`

**Files:**
- Modify: `enforcer/explain.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explain.py`:

```python
from enforcer.combinators import AllOf
from enforcer.matchers import RegexMatcher, ImportMatcher
from enforcer.explain import render_rule_explainer


class TestCombinatorRecursionFound:
    """recurses into combinators to explain inner matchers."""

    @pytest.mark.parametrize("combinator_factory", [
        lambda: AllOf([RegexMatcher(pattern=r"x"), RegexMatcher(pattern=r"y")]),
    ])
    def test_renders_inner_matchers(self, combinator_factory):
        combinator = combinator_factory()
        rule = Rule(
            id="combo-rule",
            severity=Severity.ERROR,
            matchers=[combinator],
            file_globs=["*.py"],
            message="m",
        )
        text = render_rule_explainer(rule, workspace=".")
        # the combinator itself is listed
        assert "AllOf" in text
        # inner matchers are reflected
        assert "RegexMatcher" in text


class TestCombinatorRecursionClean:
    """handles nested combinators without crash."""

    def test_nested_combinator(self):
        nested = AllOf([AllOf([RegexMatcher(pattern=r"z")])])
        rule = Rule(id="nested", severity=Severity.ERROR, matchers=[nested], file_globs=["*.py"], message="m")
        text = render_rule_explainer(rule, workspace=".")
        assert "Rule: nested" in text  # did not crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestCombinatorRecursionFound -v`
Expected: FAIL — current `render_matcher_explainer` doesn't descend into combinators.

- [ ] **Step 3: Write minimal implementation**

Modify `render_rule_explainer` in `enforcer/explain.py` to recurse. Replace the matchers loop with:

```python
    matchers = rule.matchers or []
    # ponytail: flatten combinators into a list of (depth, matcher) tuples for rendering
    flat: list[tuple[int, object]] = []
    def _flatten(ms: list, depth: int = 0) -> None:
        for m in ms:
            flat.append((depth, m))
            if hasattr(m, "matchers") and isinstance(m.matchers, list):
                _flatten(m.matchers, depth + 1)
            elif hasattr(m, "matcher") and m.matcher is not None:
                flat.append((depth + 1, m.matcher))
    _flatten(matchers)

    top_level = sum(1 for d, _ in flat if d == 0)
    lines.append(f"Matchers ({top_level}):")
    for depth, matcher in flat:
        explainer = render_matcher_explainer(matcher)
        indent = "  " * (depth + 1)
        lines.append(f"{indent}{explainer.class_name}")
        for label in ("What", "Ignores", "Basis", "shared_ctx"):
            if label in explainer.docstring_sections:
                lines.append(f"{indent}{' ' * 13}{label + ':':12} {explainer.docstring_sections[label]}")
        for param, value in explainer.configured_params.items():
            lines.append(f"{indent}{' ' * 13}{param}: {value!r}")

        test_path = _find_paired_test(explainer.class_name, workspace)
        if test_path and depth == 0:
            example = _extract_worked_example(test_path, explainer.class_name)
            if example:
                lines.append("")
                lines.append(f"{indent}{' ' * 13}Worked example ({example.file_path}:{example.test_class_name}.{example.test_method_name}):")
                for snippet_line in example.snippet.splitlines():
                    lines.append(f"{indent}{' ' * 17}{snippet_line}")
        lines.append("")
```

Also update `render_rule_explainer_json` similarly:

```python
    flat: list[tuple[int, object]] = []
    def _flatten(ms: list, depth: int = 0) -> None:
        for m in ms:
            flat.append((depth, m))
            if hasattr(m, "matchers") and isinstance(m.matchers, list):
                _flatten(m.matchers, depth + 1)
            elif hasattr(m, "matcher") and m.matcher is not None:
                flat.append((depth + 1, m.matcher))
    _flatten(rule.matchers or [])

    matchers_data = []
    for depth, matcher in flat:
        explainer = render_matcher_explainer(matcher)
        test_path = _find_paired_test(explainer.class_name, workspace)
        example = _extract_worked_example(test_path, explainer.class_name) if test_path else None
        matchers_data.append({
            "depth": depth,
            "class_name": explainer.class_name,
            "docstring_sections": explainer.docstring_sections,
            "configured_params": {k: repr(v) for k, v in explainer.configured_params.items()},
            "paired_test": str(test_path) if test_path else None,
            "worked_example": {
                "test_class": example.test_class_name,
                "test_method": example.test_method_name,
                "snippet": example.snippet,
                "file_path": example.file_path,
                "line": example.line,
            } if example else None,
        })
```

Replace the existing matchers loop in `render_rule_explainer_json` with the above.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/explain.py tests/test_explain.py
git commit -m "feat(explain): recurse into combinators to explain inner matchers"
```

---

### Task 9: Retrofit `RegexMatcher` docstring (4-section convention)

**Files:**
- Modify: `enforcer/matchers/regex.py`
- Test: `tests/test_explain.py` (re-enable assertions)

- [ ] **Step 1: Write the failing test (re-enable)**

In `tests/test_explain.py`, in `TestRenderRuleExplainerFound.test_contains_field`, restore the commented-out assertions:

```python
    @pytest.mark.parametrize("field", [
        "Rule: no-print",
        "Severity: ERROR",
        "Applies to: enforcer/**/*.py",
        "Matchers (1):",
        "RegexMatcher",
        "What:",
        "Basis:",
        "Worked example",
    ])
    def test_contains_field(self, field):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=str(Path(__file__).resolve().parent.parent))
        assert field in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestRenderRuleExplainerFound -v`
Expected: FAIL on `"What:"` and `"Basis:"` — RegexMatcher docstring doesn't have structured sections.

- [ ] **Step 3: Retrofit the docstring**

Replace `enforcer/matchers/regex.py` class docstring:

```python
@dataclass
class RegexMatcher:
    """Matches lines against a regex pattern. Returns one Match per line that matches.

    What:       flags any line where `pattern` matches at least once
    Ignores:    multiline patterns (operates line-by-line); non-matching lines
    Basis:      RAW (regex on raw file text, line-by-line)
    shared_ctx: none (stateless, reads only file_ctx.raw)
    """
    pattern: str | Pattern
    needs: Needs = Needs.RAW
    redact: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/regex.py tests/test_explain.py
git commit -m "docs(regex): retrofit RegexMatcher docstring to 4-section convention"
```

---

### Task 10: Retrofit remaining 19 matcher docstrings

**Files:**
- Modify: `enforcer/matchers/line_count.py`, `char_count.py`, `path_pattern.py`, `allowlist.py`, `ast_node.py`, `comment_density.py`, `always.py`, `file_exists.py`, `import_matcher.py`, `function_complexity.py`, `paired_file.py`, `branch_name.py`, `commit_message.py`, `naming_convention.py`, `duplicate_code.py`, `docstring.py`, `llm_check.py`, `doc_sync.py`, `keyset_sync.py`

- [ ] **Step 1: Write a verification test**

Append to `tests/test_explain.py`:

```python
import inspect
from enforcer import matchers as matcher_pkg


class TestAllMatchersHaveStructuredDocstring:
    """every exported matcher class has What: and Basis: in its docstring."""

    @pytest.mark.parametrize("class_name", matcher_pkg.__all__)
    def test_has_what_and_basis(self, class_name):
        cls = getattr(matcher_pkg, class_name)
        doc = inspect.getdoc(cls) or ""
        sections = _parse_docstring_sections(doc)
        assert "What" in sections, f"{class_name} missing 'What:' docstring section"
        assert "Basis" in sections, f"{class_name} missing 'Basis:' docstring section"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestAllMatchersHaveStructuredDocstring -v`
Expected: FAIL on all matchers except `RegexMatcher` (retrofitted in Task 9).

- [ ] **Step 3: Retrofit each matcher docstring**

For each of the following matchers, replace the class docstring with the 4-section format. Read the existing class to determine the correct content. Example for `ImportMatcher`:

```python
@dataclass
class ImportMatcher:
    """Walks the tree-sitter AST for import statements, flags any whose text matches a forbidden regex.

    What:       flags import statements matching any forbidden regex pattern
    Ignores:    non-import statements; imports not matching forbidden patterns
    Basis:      AST_PY (tree-sitter AST, iterative DFS walk)
    shared_ctx: none (stateless, reads file_ctx.ast)
    """
```

Apply the same pattern to all 19 matchers. Use the matcher's existing class docstring + module docstring + source to determine the correct `What:` and `Basis:` values. For AST matchers, `Basis:` is `AST_PY` or `AST_TS`. For regex matchers, `RAW`. For cross-file matchers, note the `shared_ctx` keys.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py::TestAllMatchersHaveStructuredDocstring -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regression**

Run: `pytest --tb=short -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/*.py tests/test_explain.py
git commit -m "docs(matchers): retrofit all matcher docstrings to 4-section convention"
```

---

### Task 11: `enforcer explain` CLI command

**Files:**
- Modify: `enforcer/cli.py`
- Test: `tests/test_cli_explain.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_explain.py`:

```python
"""Tests for `enforcer explain` CLI command."""
import pytest
from click.testing import CliRunner
from enforcer.cli import cli


_CONFIG = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

WORKSPACE = "."

RULES = [
    Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\\s*print\\s*\\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found.",
        fix_instruction="Replace print().",
        rationale="print() pollutes stdout.",
    ),
    Rule(
        id="max-lines",
        severity=Severity.WARN,
        matchers=[],
        file_globs=["README.md"],
        message="README too long.",
    ),
]
'''


def _write_config(tmp_path):
    cfg = tmp_path / "enforcer_config.py"
    cfg.write_text(_CONFIG)
    return str(cfg)


class TestCliExplainFound:
    """renders an explainer for a valid rule id."""

    @pytest.mark.parametrize("rule_id", ["no-print", "max-lines"])
    def test_explains_existing_rule(self, rule_id, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", rule_id, "--config", cfg])
        assert result.exit_code == 0
        assert f"Rule: {rule_id}" in result.output

    def test_includes_matcher_detail(self, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", "no-print", "--config", cfg])
        assert "RegexMatcher" in result.output
        assert "What:" in result.output


class TestCliExplainClean:
    """handles unknown rule ids gracefully."""

    @pytest.mark.parametrize("bad_id", ["nonexistent", "totally-fake"])
    def test_unknown_rule_suggests(self, bad_id, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", bad_id, "--config", cfg])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no rule" in result.output.lower()

    def test_json_format(self, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", "no-print", "--config", cfg, "--format", "json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["rule_id"] == "no-print"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_explain.py -v`
Expected: FAIL with `Error: No such command 'explain'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/cli.py` (before the `if __name__ == "__main__":` block):

```python
@cli.command()
@click.argument("rule_id")
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]))
def explain(rule_id, config_path, fmt):
    """Explain what a rule matches, what it ignores, and show a worked example."""
    from enforcer.explain import load_rule_for_explain, render_rule_explainer, render_rule_explainer_json

    result = load_rule_for_explain(config_path, rule_id)
    if result.rule is None:
        click.echo(f"No rule with id '{rule_id}'.", err=True)
        if result.suggestions:
            click.echo("Did you mean one of: " + ", ".join(result.suggestions) + "?", err=True)
        sys.exit(1)

    if fmt == "json":
        import json
        click.echo(json.dumps(render_rule_explainer_json(result.rule, workspace=result.config_workspace), indent=2))
    else:
        click.echo(render_rule_explainer(result.rule, workspace=result.config_workspace))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_explain.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/cli.py tests/test_cli_explain.py
git commit -m "feat(cli): add `enforcer explain <rule-id>` command"
```

---

### Task 12: Docs generator — Matchers block

**Files:**
- Modify: `enforcer/docs.py`
- Test: `tests/test_docs.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docs.py`:

```python
import inspect
from enforcer.docs import _render_rule_doc, render_rules_doc


class TestRenderDocMatchersBlock:
    """renders a Matchers block with class name and What: line."""

    @pytest.mark.parametrize("present_substring", [
        "**Matchers:**",
        "RegexMatcher",
    ])
    def test_matchers_block_present(self, present_substring):
        rules = [
            Rule(
                id="no-print",
                severity=Severity.ERROR,
                matchers=[RegexMatcher(r"^\s*print\s*\(")],
                file_globs=["*.py"],
                message="m",
            ),
        ]
        md = render_rules_doc(rules)
        assert present_substring in md

    def test_matchers_block_omitted_when_no_matchers(self):
        rules = [
            Rule(id="empty", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        ]
        md = render_rules_doc(rules)
        assert "**Matchers:**" not in md

    def test_matchers_block_links_paired_test(self):
        rules = [
            Rule(
                id="no-print",
                severity=Severity.ERROR,
                matchers=[RegexMatcher(r"^\s*print\s*\(")],
                file_globs=["*.py"],
                message="m",
            ),
        ]
        md = render_rules_doc(rules)
        assert "test_regex" in md  # paired test path referenced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docs.py::TestRenderDocMatchersBlock -v`
Expected: FAIL — `_render_rule_doc` doesn't emit a Matchers block.

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/docs.py` (after the existing imports):

```python
import inspect
```

Modify `_render_rule_doc` to call a new `_render_matchers_doc` and append its output. Replace the function body:

```python
def _render_rule_doc(rule: Rule) -> list[str]:
    """Render a single rule as natural-language markdown lines."""
    out: list[str] = []
    out.append(f"### {rule.id}")
    out.append("")
    out.extend(_render_message_doc(rule))
    out.extend(_render_rationale_doc(rule))
    out.extend(_render_target_doc(rule))
    out.extend(_render_matchers_doc(rule))
    out.extend(_render_optional_doc(rule))
    return out


def _render_matchers_doc(rule: Rule) -> list[str]:
    """Render matchers as a markdown block: class name + What: line + paired test link."""
    if not rule.matchers:
        return []
    out: list[str] = ["**Matchers:**", ""]
    for matcher in rule.matchers:
        cls_name = type(matcher).__name__
        doc = inspect.getdoc(matcher) or ""
        what_line = ""
        for line in doc.splitlines():
            stripped = line.strip()
            if stripped.startswith("What:"):
                what_line = stripped[len("What:"):].strip()
                break
        if what_line:
            out.append(f"- `{cls_name}` — {what_line}")
        else:
            out.append(f"- `{cls_name}`")
    out.append("")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_docs.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regression**

Run: `pytest tests/test_docs.py tests/test_cli_docs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/docs.py tests/test_docs.py
git commit -m "feat(docs): add Matchers block to rendered convention docs"
```

---

### Task 13: `TestCoverageMatcher` — AST inspection of test files

**Files:**
- Create: `enforcer/matchers/test_coverage.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_test_coverage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_matchers/test_test_coverage.py`:

```python
"""Tests for TestCoverageMatcher: enforces positive+negative parameterized test coverage."""
import pytest
from pathlib import Path
from enforcer.matchers.test_coverage import TestCoverageMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(test_source: str, path: str = "test_x.py") -> FileContext:
    ctx = FileContext(path=path, raw=test_source)
    from enforcer.parsers.tree_sitter import parse
    ctx.ast = parse(test_source, Needs.AST_PY)
    return ctx


_GOOD_TEST = '''\
import pytest
from enforcer.matchers.regex import RegexMatcher

class TestRegexMatcherFlags:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_flagged(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert len(matches) == 1

class TestRegexMatcherClean:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_no_match(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert not matches
'''


_MISSING_NEGATIVE = '''\
import pytest
from enforcer.matchers.regex import RegexMatcher

class TestRegexMatcherFlags:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_flagged(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert len(matches) == 1
'''

_MISSING_POSITIVE = '''\
import pytest
class TestClean:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_no_match(self, line):
        assert not []
'''

_UNDER_PARAMETRIZED = '''\
import pytest
class TestFlags:
    @pytest.mark.parametrize("line", ["a"])
    def test_flagged(self, line):
        assert True

class TestClean:
    @pytest.mark.parametrize("line", ["a"])
    def test_no_match(self, line):
        assert not []
'''

_NO_PARAMETRIZE = '''\
class TestFlags:
    def test_flagged(self):
        assert True

class TestClean:
    def test_no_match(self):
        assert not []
'''


class TestTestCoverageMatcherFlags:
    """flags test files missing positive or negative coverage, or under-parameterized."""

    @pytest.mark.parametrize("source,expected_substring", [
        (_MISSING_NEGATIVE, "negative"),
        (_MISSING_POSITIVE, "positive"),
        (_UNDER_PARAMETRIZED, "parametr"),
        (_NO_PARAMETRIZE, "parametr"),
    ])
    def test_flags_violating_test_file(self, source, expected_substring):
        ctx = _make_ctx(source)
        matcher = TestCoverageMatcher()
        matches = matcher.find(ctx)
        assert len(matches) >= 1
        assert expected_substring.lower() in matches[0].matched_value.lower() or expected_substring.lower() in matches[0].message.lower()


class TestTestCoverageMatcherClean:
    """does not flag test files with both positive and negative, each parameterized >=3."""

    @pytest.mark.parametrize("source", [
        _GOOD_TEST,
    ])
    def test_no_match_on_good_file(self, source):
        ctx = _make_ctx(source)
        matcher = TestCoverageMatcher()
        matches = matcher.find(ctx)
        assert matches == []

    def test_needs_ast_py(self):
        assert TestCoverageMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="class TestX:\n    pass\n")
        matcher = TestCoverageMatcher()
        assert matcher.find(ctx) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_test_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.matchers.test_coverage'`

- [ ] **Step 3: Write minimal implementation**

Create `enforcer/matchers/test_coverage.py`:

```python
"""TestCoverageMatcher: AST-inspects test files for positive+negative parameterized coverage."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class TestCoverageMatcher:
    """Inspects a test file's AST for positive + negative test coverage, each parameterized >=3.

    What:       flags test files missing positive (assert) or negative (assert not) cases, or with <3 parametrize cases
    Ignores:    non-test files; test classes with both sides parameterized >=3
    Basis:      AST_PY (tree-sitter AST, iterative DFS for class/method/parametrize detection)
    shared_ctx: none (stateless, reads file_ctx.ast)
    """
    min_parametrize_cases: int = 3
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag test files missing positive or negative parameterized coverage. Returns list of Match."""
        if not file_ctx.ast:
            return []
        from enforcer.parsers.ast_utils import walk_ast, node_text

        root = file_ctx.ast.root_node
        has_positive = False
        has_negative = False
        positive_param_count = 0
        negative_param_count = 0

        for node in walk_ast(root):
            if node.type != "function_definition":
                continue
            method_name = self._extract_name(node)
            if not method_name or not method_name.startswith("test_"):
                continue
            is_positive, is_negative, param_count = self._classify_method(node, root)
            if is_positive:
                has_positive = True
                positive_param_count = max(positive_param_count, param_count)
            if is_negative:
                has_negative = True
                negative_param_count = max(negative_param_count, param_count)

        matches: list[Match] = []
        if not has_positive:
            matches.append(Match(
                file=file_ctx.path, line=0,
                matched_value="missing positive test (assert on match list, parametrized >=3)",
                message="No positive test case found.",
            ))
        elif positive_param_count < self.min_parametrize_cases:
            matches.append(Match(
                file=file_ctx.path, line=0,
                matched_value=f"positive test parametrized with {positive_param_count} cases (min {self.min_parametrize_cases})",
                message="Positive case under-parameterized.",
            ))
        if not has_negative:
            matches.append(Match(
                file=file_ctx.path, line=0,
                matched_value="missing negative test (assert not / assert len==0, parametrized >=3)",
                message="No negative test case found.",
            ))
        elif negative_param_count < self.min_parametrize_cases:
            matches.append(Match(
                file=file_ctx.path, line=0,
                matched_value=f"negative test parametrized with {negative_param_count} cases (min {self.min_parametrize_cases})",
                message="Negative case under-parameterized.",
            ))
        return matches

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return ""

    def _classify_method(self, method_node, root) -> tuple[bool, bool, int]:
        """Return (is_positive, is_negative, parametrize_case_count) for a method node."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        is_positive = False
        is_negative = False
        param_count = 0
        for inner in walk_ast(method_node):
            # detect @pytest.mark.parametrize("...", [...]) — count the list elements
            if inner.type == "decorator":
                dec_text = node_text(inner)
                if "parametrize" in dec_text:
                    # find the list literal inside the decorator — count top-level elements
                    for sub in walk_ast(inner):
                        if sub.type == "list":
                            param_count = sum(1 for c in sub.children if c.type in ("string", "identifier", "integer", "true", "false", "none"))
                            break
            # detect assert statements — positive vs negative
            if inner.type == "assert_statement":
                assert_text = node_text(inner)
                if "assert not " in assert_text or "assert len(" in assert_text and "== 0" in assert_text:
                    is_negative = True
                elif "assert " in assert_text:
                    is_positive = True
        # name-based fallback: test_*_fail/flags -> positive, test_*_success/clean -> negative
        name = self._extract_name(method_node)
        if not is_positive and any(kw in name for kw in ("fail", "flag", "violation")):
            is_positive = True
        if not is_negative and any(kw in name for kw in ("success", "clean", "valid", "passes")):
            is_negative = True
        return is_positive, is_negative, param_count
```

Add to `enforcer/matchers/__init__.py`:

```python
from enforcer.matchers.test_coverage import TestCoverageMatcher
```

And add `"TestCoverageMatcher",` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matchers/test_test_coverage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/test_coverage.py enforcer/matchers/__init__.py tests/test_matchers/test_test_coverage.py
git commit -m "feat(matchers): add TestCoverageMatcher for positive/negative test coverage"
```

---

### Task 14: `matcher-docstring-structured` self-enforcement rule

**Files:**
- Modify: `enforcer_config.py`
- Test: `tests/test_integration.py` (or verify via the rule itself)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_explain.py` (since it's docstring-related):

```python
class TestMatcherDocstringStructuredRule:
    """the matcher-docstring-structured rule is configured and would catch missing What:."""

    def test_rule_exists_in_config(self):
        from enforcer.config import load_config
        config = load_config("enforcer_config.py")
        rule_ids = [r.id for r in config.rules]
        assert "matcher-docstring-structured" in rule_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestMatcherDocstringStructuredRule -v`
Expected: FAIL — rule not yet in config.

- [ ] **Step 3: Add the rule to config**

Add to `enforcer_config.py` (after the `extractor-test-paired` rule, in the ERROR section):

```python
    # ─── Docstring convention: matchers must declare What: and Basis: ────
    Rule(
        id="matcher-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\\s+\\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py", "enforcer/matchers/test_coverage.py"],
        message="Matcher class at {file}:{line} docstring missing 'What:' or 'Basis:' section.",
        fix_instruction="Add 'What: <what it flags>' and 'Basis: <RAW|AST_PY|AST_TS|AST_CSS>' lines to the class docstring.",
        diff_only=True,
        rationale="Matchers without structured docstrings can't be explained by `enforcer explain`. The What:/Basis: sections are the minimum for self-documentation.",
    ),
```

**Note:** This regex is a rough heuristic. A more robust implementation would use an AST-based matcher (`AstNodeMatcher` walking class definitions and checking their docstring). For the first cut, the regex catches the most common case (class without `What:` in docstring). Refine to AST in a follow-up if false positives appear.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py::TestMatcherDocstringStructuredRule -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer_config.py tests/test_explain.py
git commit -m "feat(config): add matcher-docstring-structured self-enforcement rule"
```

---

### Task 15: `matcher-test-positive-negative` self-enforcement rule

**Files:**
- Modify: `enforcer_config.py`
- Test: `tests/test_explain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_explain.py`:

```python
class TestMatcherTestPositiveNegativeRule:
    """the matcher-test-positive-negative rule is configured."""

    def test_rule_exists_in_config(self):
        from enforcer.config import load_config
        config = load_config("enforcer_config.py")
        rule_ids = [r.id for r in config.rules]
        assert "matcher-test-positive-negative" in rule_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_explain.py::TestMatcherTestPositiveNegativeRule -v`
Expected: FAIL

- [ ] **Step 3: Add the rule to config**

Add to `enforcer_config.py` (after `matcher-docstring-structured`):

```python
    # ─── Test coverage: matchers must have positive+negative parametrized tests ──
    Rule(
        id="matcher-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_matchers/*.py"],
        exclude_globs=["tests/test_matchers/__init__.py", "tests/test_matchers/test_test_coverage.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_fail, assert on match list) and negative case (test_*_success, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Matchers enforce conventions; tests enforce matchers. Without both positive and negative parameterized cases, matcher regressions go undetected.",
    ),
```

Add `TestCoverageMatcher` to the import block at the top of `enforcer_config.py`:

```python
from enforcer.matchers import (
    RegexMatcher,
    ImportMatcher,
    FunctionComplexityMatcher,
    PairedFileMatcher,
    BranchNameMatcher,
    CommitMessageMatcher,
    NamingConventionMatcher,
    DocstringMatcher,
    AlwaysMatcher,
    LineCountMatcher,
    LLMMatcher,
    DocSyncMatcher,
    TestCoverageMatcher,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_explain.py::TestMatcherTestPositiveNegativeRule -v`
Expected: PASS

- [ ] **Step 5: Run the enforcer against itself to verify no violations**

Run: `ENFORCER_CONFIG=enforcer_config.py python -m enforcer.cli check --all`
Expected: May flag existing test files that don't meet the convention yet — that's expected (diff_only means it only fires on `--staged`). No action needed for `--all`.

- [ ] **Step 6: Commit**

```bash
git add enforcer_config.py tests/test_explain.py
git commit -m "feat(config): add matcher-test-positive-negative self-enforcement rule"
```

---

### Task 16: MCP server — `explain_rule` tool

**Files:**
- Modify: `enforcer/mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_server.py`:

```python
class TestMcpExplainRule:
    """the explain_rule MCP tool returns structured rule explainer."""

    def test_explain_rule_returns_json(self, tmp_path, monkeypatch):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        monkeypatch.setenv("ENFORCER_CONFIG", str(cfg))
        from enforcer.mcp_server import explain_rule
        result = explain_rule("no-print")
        import json
        data = json.loads(result)
        assert data["rule_id"] == "no-print"
        assert data["severity"] == "error"

    def test_explain_rule_unknown_returns_error(self, tmp_path, monkeypatch):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        monkeypatch.setenv("ENFORCER_CONFIG", str(cfg))
        from enforcer.mcp_server import explain_rule
        result = explain_rule("nonexistent")
        import json
        data = json.loads(result)
        assert "error" in data or "not found" in result.lower()

    def test_explain_rule_in_tool_definitions(self):
        from enforcer.mcp_server import _tool_definitions
        tools = _tool_definitions()
        names = [t["name"] for t in tools]
        assert "explain_rule" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_server.py::TestMcpExplainRule -v`
Expected: FAIL with `ImportError: cannot import name 'explain_rule'`

- [ ] **Step 3: Write minimal implementation**

Add to `enforcer/mcp_server.py` (after `verify_fix`):

```python
def explain_rule(rule_id: str) -> str:
    """Explain a rule: what it matches, what it ignores, worked example. Returns JSON."""
    import json
    from enforcer.explain import load_rule_for_explain, render_rule_explainer_json
    result = load_rule_for_explain(_config_path(), rule_id)
    if result.rule is None:
        return json.dumps({"error": f"No rule with id '{rule_id}'", "suggestions": result.suggestions})
    return json.dumps(render_rule_explainer_json(result.rule, workspace=result.config_workspace), indent=2)
```

Add to `_tool_definitions()`:

```python
        {
            "name": "explain_rule",
            "description": "Explain what a rule matches, what it ignores, and show a worked example",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                },
                "required": ["rule_id"],
            },
        },
```

Add to `_handle_tool_call`:

```python
    if tool_name == "explain_rule":
        return explain_rule(rule_id=args.get("rule_id"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp_server.py::TestMcpExplainRule -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): add explain_rule tool to MCP server"
```

---

### Task 17: Update AGENTS.md matcher development contract

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the matcher development contract**

In `AGENTS.md`, under "## Adding a New Matcher", add after step 6 (before "Run `pytest`"):

```markdown
7. **Document the matcher with a structured docstring.** Class docstring must include `What:` (what it flags) and `Basis:` (RAW/AST_PY/AST_TS/AST_CSS) sections. Example:

   ```python
   @dataclass
   class MyMatcher:
       """One-line summary.

       What:       flags <what>
       Ignores:    <what it doesn't catch>
       Basis:      <RAW or AST_*>
       shared_ctx: <keys or none>
       """
   ```

8. **Write positive and negative parameterized tests.** Test file must contain:
   - Positive case: `test_*_fail` / `test_*_flags` — uses `assert` on a non-empty match list. Parameterized with >=3 examples via `@pytest.mark.parametrize`.
   - Negative case: `test_*_success` / `test_*_clean` — uses `assert not` or `assert len(...) == 0`. Parameterized with >=3 examples.
   - Minimum: 2 parameterized methods × 3 examples = 6 cases per matcher.
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): document structured docstring + positive/negative test conventions"
```

---

### Task 18: Regenerate CONVENTIONS.md

**Files:**
- Modify: `CONVENTIONS.md`

- [ ] **Step 1: Regenerate the doc**

Run: `python -m enforcer.cli sync-doc`
Expected: `CONVENTIONS.md` updated with the two new rules + Matchers blocks.

- [ ] **Step 2: Verify the new rules appear**

Run: `grep -c "matcher-docstring-structured\|matcher-test-positive-negative" CONVENTIONS.md`
Expected: `2`

- [ ] **Step 3: Commit**

```bash
git add CONVENTIONS.md
git commit -m "docs: regenerate CONVENTIONS.md with new rules + Matchers blocks"
```

---

### Task 19: Full test suite + final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest --tb=short -q`
Expected: All tests PASS.

- [ ] **Step 2: Run the enforcer against itself (staged mode)**

Run: `ENFORCER_CONFIG=enforcer_config.py python -m enforcer.cli check --all`
Expected: No violations (or only diff_only rules suppressed — which is correct behavior).

- [ ] **Step 3: Run `enforcer explain` on a real rule**

Run: `python -m enforcer.cli explain no-print`
Expected: Renders the full explainer with matcher detail, docstring sections, and a worked example.

- [ ] **Step 4: Run `enforcer explain` with JSON format**

Run: `python -m enforcer.cli explain no-print --format json | python -m json.tool`
Expected: Valid JSON with `rule_id`, `matchers` array.

- [ ] **Step 5: Final commit (if any cleanup)**

```bash
git add -A
git commit -m "chore: final cleanup for rule clarity feature" || echo "nothing to commit"
```

---

## Self-Review

**1. Spec coverage:**
- Part 1 (docstring conventions): Tasks 9, 10, 14 ✓
- Part 2 (paired tests as worked examples): Task 13 (TestCoverageMatcher), Task 17 (AGENTS.md) ✓
- Part 3 (`enforcer explain` command): Tasks 1-8, 11 ✓
- Part 4 (docs generator enhancement): Task 12 ✓
- Part 5 (TestCoverageMatcher + enforcement rules): Tasks 13, 14, 15 ✓
- MCP integration: Task 16 ✓
- Migration (retrofit 20 matchers): Tasks 9, 10 ✓

**2. Placeholder scan:** No TBD/TODO in steps. Task 10 step 3 says "for each of the following matchers" — the list is the file list at the top, all 19 named. The instruction to "read the existing class" is the action; the engineer determines content from the source. This is acceptable (not a placeholder — it's a mechanical task with a clear pattern from Task 9).

**3. Type consistency:** `MatcherExplainer`, `WorkedExample`, `ExplainResult` dataclasses defined in Tasks 1-7 and used consistently. `render_matcher_explainer` returns `MatcherExplainer` in Task 2, used in Tasks 5, 6, 8. `_find_paired_test` returns `Path | None` in Task 3, used in Tasks 4, 5, 6, 8. `_extract_worked_example` returns `WorkedExample | None` in Task 4, used in Tasks 5, 6, 8. `TestCoverageMatcher` defined in Task 13, used in Task 15. All signatures match. ✓
