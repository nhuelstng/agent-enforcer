# Dogfood Phase 3: Config Split + Reviewer Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic 866-line `enforcer_config.py` into a focused `enforcer_config/` package (7 files, each under 200 lines), fix `CanonicalImportMatcher` multi-name import UX, and remove obsolete exemptions.

**Architecture:** Replace single-file config with a Python package. Each sub-config file defines a `*_RULES` list; `__init__.py` composes them into `RULES`. Update `load_config()` to handle both file paths (`.py` suffix → `spec_from_file_location`) and package names (→ `import_module`). Fix the matcher to emit one `Match` per non-canonical symbol instead of one per import statement.

**Tech Stack:** Python 3.11+, importlib, tree-sitter, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `enforcer/matchers/canonical_import.py` | Fix: emit per-symbol matches, rename `_has_non_canonical` → `_non_canonical_names` |
| `tests/test_matchers/test_canonical_import.py` | Update: assert per-symbol match count and `matched_value` |
| `enforcer/config.py` | Fix: `load_config()` handle package names (not just `.py` files) |
| `tests/test_config.py` | Add: test for package loading |
| `enforcer_config/__init__.py` | Composition: imports all `*_RULES`, defines `RULES`, `WORKSPACE`, `SEVERITY_ACTIONS`, `LLM_CONFIG` |
| `enforcer_config/git_rules.py` | 2 rules: branch-naming, commit-message |
| `enforcer_config/test_rules.py` | 13 rules: test pairing (5), test coverage (4), docstring conventions (4) |
| `enforcer_config/arch_rules.py` | 9 rules: layer deps, private imports, canonical imports, layer direction (5), config hygiene (2) |
| `enforcer_config/style_rules.py` | 9 rules: nesting, interface, file length, function complexity (3), wildcard imports, TODO owner, docstrings |
| `enforcer_config/hygiene_rules.py` | 11 rules: all-sorted, side-effects, constants, magic numbers, naming (2), no-print, bare-except, no-secrets, no-debug, no-type-ignore, no-scratch-files |
| `enforcer_config/self_enforce.py` | 11 rules: reminders (6), CONVENTIONS.md sync, README LLM, commit-msg LLM, facade (2) |
| `enforcer/cli.py` | Update: default `--config` from `enforcer_config.py` → `enforcer_config` |
| `enforcer/mcp_server.py` | Update: default `ENFORCER_CONFIG` from `enforcer_config.py` → `enforcer_config` |
| `enforcer_config.py` | Delete (replaced by package) |
| `tests/test_explain.py` | Update: `load_config("enforcer_config.py")` → `load_config("enforcer_config")` |
| `tests/test_matchers/test_doc_sync.py` | Update: `load_config("enforcer_config.py")` → `load_config("enforcer_config")` |
| `tests/test_cli_refactor.py` | Update: write temp config to `enforcer_config.py` in tmpdir, pass `--config` explicitly |
| `CONVENTIONS.md` | Regenerate via `enforcer sync-doc` |

---

## Task 1: Fix CanonicalImportMatcher multi-name import UX

**Files:**
- Modify: `tests/test_matchers/test_canonical_import.py`
- Modify: `enforcer/matchers/canonical_import.py`

- [ ] **Step 1: Update tests to expect per-symbol matches**

Replace the entire test file content:

```python
"""Tests for CanonicalImportMatcher: enforces symbols imported from canonical module."""
import pytest
from enforcer.matchers.canonical_import import CanonicalImportMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


@pytest.mark.parametrize("source,expected_count", [
    ("from enforcer.rule import _glob_match\n", 1),
    ("from enforcer.rule import _glob_match as gm\n", 1),
    ("from enforcer.rule import Rule, _glob_match\n", 1),
    ("from enforcer.rule import Rule as r, _glob_match as gm\n", 1),
    ("from enforcer.rule import _glob_match, glob_match\n", 2),
])
def test_canonical_import_fail(source, expected_count):
    """Should flag imports of canonical-mapped symbols from non-canonical modules."""
    canonical = {"_glob_match": "enforcer.glob_util", "glob_match": "enforcer.glob_util"}
    matches = CanonicalImportMatcher(canonical=canonical).find(_make_ctx(source))
    assert len(matches) == expected_count


def test_canonical_import_matched_value_descriptive():
    """matched_value should name the symbol and canonical module, not the full import line."""
    canonical = {"_glob_match": "enforcer.glob_util"}
    source = "from enforcer.rule import Rule, _glob_match\n"
    matches = CanonicalImportMatcher(canonical=canonical).find(_make_ctx(source))
    assert len(matches) == 1
    assert "_glob_match" in matches[0].matched_value
    assert "enforcer.glob_util" in matches[0].matched_value


@pytest.mark.parametrize("source", [
    "from enforcer.glob_util import _glob_match\n",
    "from enforcer.rule import Rule\n",
    "import enforcer.rule\n",
    "from . import foo\n",
    "from .rule import _glob_match\n",
])
def test_canonical_import_success(source):
    """Should not flag imports from canonical modules, unknown symbols, or relative imports."""
    canonical = {"_glob_match": "enforcer.glob_util"}
    matches = CanonicalImportMatcher(canonical=canonical).find(_make_ctx(source))
    assert matches == []


def test_canonical_import_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="from enforcer.rule import _glob_match")
    canonical = {"_glob_match": "enforcer.glob_util"}
    assert CanonicalImportMatcher(canonical=canonical).find(ctx) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_matchers/test_canonical_import.py -v`
Expected: FAIL — `test_canonical_import_fail` expects 1 match for multi-name import but gets 1 (old behavior emits 1 per statement, not per symbol). The `test_canonical_import_fail` with 2 non-canonical names expects 2 but gets 1. `test_canonical_import_matched_value_descriptive` fails because `matched_value` is the full import line.

- [ ] **Step 3: Fix the matcher to emit per-symbol matches**

Replace `enforcer/matchers/canonical_import.py` with:

```python
"""CanonicalImportMatcher: enforces symbols are imported from their canonical module."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class CanonicalImportMatcher:
    """Enforces that symbols are imported from their canonical module, not re-exporting modules.

    What:       flags `from <module> import <symbol>` when <symbol> is in the canonical map
                and <module> is not the canonical source; emits one Match per non-canonical symbol
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
            for name in self._non_canonical_names(module, names):
                matches.append(self._build_match(file_ctx.path, node, name, module))
        return matches

    def _non_canonical_names(self, module: str, names: list[str]) -> list[str]:
        """Return names imported from a non-canonical module."""
        result: list[str] = []
        for name in names:
            canonical_module = self.canonical.get(name)
            if canonical_module is not None and module != canonical_module:
                result.append(name)
        return result

    @staticmethod
    def _build_match(file_path: str, node, name: str, module: str) -> Match:
        """Build a Match for a non-canonical import symbol."""
        canonical_module = ""
        return Match(
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1] + 1,
            matched_value=f"{name} (from {module}, should be from {CanonicalImportMatcher._canonical_for(name)})",
        )

    @staticmethod
    def _canonical_for(name: str) -> str:
        """Placeholder — see note below. Actually we need access to self.canonical here."""
        return ""

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
            resolved = CanonicalImportMatcher._resolve_name_node(name_node)
            if resolved is None:
                continue
            name = node_text(resolved)
            if isinstance(name, bytes):
                name = name.decode()
            names.append(name)
        return module, names

    @staticmethod
    def _resolve_name_node(name_node):
        """Resolve an imported name node, unwrapping aliased_import wrappers. Returns dotted_name node or None."""
        if name_node.type != "aliased_import":
            return name_node
        return next((cc for cc in name_node.children if cc.type == "dotted_name"), None)
```

**Wait** — `_build_match` is `@staticmethod` but needs `self.canonical` to look up the canonical module. Fix: make it an instance method. Replace the `_build_match` and remove `_canonical_for`:

```python
    def _build_match(self, file_path: str, node, name: str, module: str) -> Match:
        """Build a Match for a non-canonical import symbol."""
        canonical_module = self.canonical.get(name, "")
        return Match(
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1] + 1,
            matched_value=f"{name} (from {module}, should be from {canonical_module})",
        )
```

And update the call site in `find()`: `matches.append(self._build_match(file_ctx.path, node, name, module))` (already correct since it's `self.`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_canonical_import.py -v`
Expected: PASS — all 8 tests pass.

- [ ] **Step 5: Run enforcer self-check on the matcher**

Run: `python -m enforcer.cli check --paths enforcer/matchers/canonical_import.py`
Expected: No issues found (or only pre-existing issues unrelated to this change).

- [ ] **Step 6: Commit**

```bash
git add tests/test_matchers/test_canonical_import.py enforcer/matchers/canonical_import.py
git commit -s -m "fix(matchers): CanonicalImportMatcher emits per-symbol matches

One Match per non-canonical symbol instead of one per import statement.
matched_value now names the symbol and canonical module, not the full
import line. Multi-name imports like 'from enforcer.rule import Rule,
_glob_match' produce one match for _glob_match only."
```

---

## Task 2: Update load_config() to support package loading

**Files:**
- Modify: `enforcer/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing test for package loading**

Add to `tests/test_config.py`:

```python
def test_load_config_from_package(tmp_path):
    """load_config should handle package directories, not just .py files."""
    import importlib
    pkg_dir = tmp_path / "my_config_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "from enforcer import Rule, Severity\n"
        "RULES = []\n"
        "WORKSPACE = '.'\n"
    )
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        config = load_config("my_config_pkg")
        assert config.rules == []
        assert config.workspace == "."
    finally:
        sys.path.remove(str(tmp_path))
        # Clean up cached module
        if "my_config_pkg" in sys.modules:
            del sys.modules["my_config_pkg"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_load_config_from_package -v`
Expected: FAIL — `ImportError: Cannot load config from my_config_pkg` (current `spec_from_file_location` returns None for non-file paths).

- [ ] **Step 3: Update load_config() to handle packages**

In `enforcer/config.py`, replace the `load_config` function:

```python
def load_config(config_path: str) -> Config:
    """Load config from a .py file path or a package name. Extracts RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG.

    If config_path ends in .py or contains a path separator, treat it as a file path
    (spec_from_file_location). Otherwise, treat it as an importable package/module name
    (importlib.import_module).
    """
    import sys

    if config_path.endswith(".py") or "/" in config_path or os.sep in config_path:
        spec = importlib.util.spec_from_file_location("enforcer_config", config_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load config from {config_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(config_path)

    return Config(
        rules=getattr(module, "RULES", []),
        workspace=getattr(module, "WORKSPACE", "."),
        severity_actions=getattr(module, "SEVERITY_ACTIONS", {
            Severity.ERROR: "block",
            Severity.WARN: "print",
            Severity.INFO: "hint",
        }),
        llm_config=_coerce_llm_config(getattr(module, "LLM_CONFIG", LLMConfig())),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_load_config_from_package -v`
Expected: PASS

- [ ] **Step 5: Run full config test suite**

Run: `pytest tests/test_config.py -v`
Expected: PASS — all tests pass (existing file-based tests still work via `spec_from_file_location`).

- [ ] **Step 6: Commit**

```bash
git add enforcer/config.py tests/test_config.py
git commit -s -m "feat(config): load_config supports package names

If config_path doesn't end in .py or contain a path separator, use
importlib.import_module instead of spec_from_file_location. Enables
config as a Python package (enforcer_config/) instead of a single file."
```

---

## Task 3: Create enforcer_config/ package — sub-config files

**Files:**
- Create: `enforcer_config/git_rules.py`
- Create: `enforcer_config/test_rules.py`
- Create: `enforcer_config/arch_rules.py`
- Create: `enforcer_config/style_rules.py`
- Create: `enforcer_config/hygiene_rules.py`
- Create: `enforcer_config/self_enforce.py`
- Create: `enforcer_config/__init__.py`

This task creates all sub-config files. The old `enforcer_config.py` remains in place — both coexist temporarily. The new package shadows the old file in Python's import system only when loaded by name; `load_config("enforcer_config.py")` still loads the old file. We'll switch defaults in Task 4.

- [ ] **Step 1: Create `enforcer_config/git_rules.py`**

```python
"""Git metadata rules: branch naming and commit message format."""
from enforcer import Rule, Severity, RuleType
from enforcer.matchers import BranchNameMatcher, CommitMessageMatcher

GIT_RULES = [
    Rule(
        id="branch-naming",
        severity=Severity.ERROR,
        matchers=[BranchNameMatcher(pattern=r"^(feature|fix|chore|docs|refactor)/")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Branch '{matched_value}' doesn't match required pattern: type/description",
        fix_instruction="Rename: git branch -m <type>/<description>",
        rationale="Branches encode intent; CI/greps depend on the type/ prefix to route checks and changelogs.",
    ),
    Rule(
        id="commit-message",
        severity=Severity.ERROR,
        matchers=[CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Commit message '{matched_value}' doesn't follow Conventional Commits",
        fix_instruction="Use: type(scope): description (e.g. feat(matchers): add X)",
        rationale="Conventional Commits enable automated changelog generation and semantic versioning. Unstructured messages break tooling.",
    ),
]
```

- [ ] **Step 2: Create `enforcer_config/test_rules.py`**

```python
"""Test pairing and test coverage rules."""
from enforcer import Rule, Severity
from enforcer.matchers import PairedFileMatcher, RegexMatcher, TestCoverageMatcher

TEST_RULES = [
    Rule(
        id="matcher-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/matchers/*.py",
            derived_glob="tests/test_matchers/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py"],
        message="No test file for matcher {file}. Every matcher needs paired tests.",
        fix_instruction="Create tests/test_matchers/test_{stem}.py",
        diff_only=True,
        rationale="Untested matchers ship false positives/negatives silently. Paired tests catch regressions before they reach users.",
    ),
    Rule(
        id="predicate-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/predicates/*.py",
            derived_glob="tests/test_predicates/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/predicates/*.py"],
        exclude_globs=["enforcer/predicates/__init__.py"],
        message="No test file for predicate {file}. Every predicate needs paired tests.",
        fix_instruction="Create tests/test_predicates/test_{stem}.py",
        diff_only=True,
        rationale="Predicates filter matches; untested predicates can silently suppress real violations or let false ones through.",
    ),
    Rule(
        id="combinator-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/combinators/*.py",
            derived_glob="tests/test_combinators/test_{stem}*.py",
            exclude_stems=["__init__", "core"],
        )],
        file_globs=["enforcer/combinators/*.py"],
        exclude_globs=["enforcer/combinators/__init__.py"],
        message="No test file for combinator {file}. Every combinator needs paired tests.",
        fix_instruction="Create tests/test_combinators/test_{stem}.py",
        diff_only=True,
        rationale="Combinators compose matcher logic; untested combinators can invert or short-circuit the intended logic.",
    ),
    Rule(
        id="core-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/*.py",
            derived_glob="tests/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/*.py"],
        exclude_globs=["enforcer/__init__.py", "enforcer/matchers/**", "enforcer/predicates/**", "enforcer/combinators/**", "enforcer/parsers/**", "enforcer/extractors/**"],
        message="No test file for core module {file}.",
        fix_instruction="Create tests/test_{stem}.py",
        diff_only=True,
        rationale="Core modules (rule, runner, context, config) are load-bearing; untested core changes can break every rule.",
    ),
    Rule(
        id="extractor-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/extractors/*.py",
            derived_glob="tests/test_extractors/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/extractors/*.py"],
        exclude_globs=["enforcer/extractors/__init__.py"],
        message="Extractor {file} has no paired test. Create tests/test_extractors/test_{stem}*.py",
        fix_instruction="Add a test file covering happy path, empty/malformed input, and format-specific edge cases.",
        diff_only=True,
        rationale="Extractors are pure string transforms — trivial to test. Missing tests mean regressions in key extraction go unnoticed.",
    ),
    Rule(
        id="matcher-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py", "enforcer/matchers/test_coverage.py"],
        message="Matcher class at {file}:{line} docstring missing 'What:' or 'Basis:' section.",
        fix_instruction="Add 'What: <what it flags>' and 'Basis: <RAW|AST_PY|AST_TS|AST_CSS>' lines to the class docstring.",
        diff_only=True,
        rationale="Matchers without structured docstrings can't be explained by `enforcer explain`. The What:/Basis: sections are the minimum for self-documentation.",
    ),
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
    Rule(
        id="predicate-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_predicates/*.py"],
        exclude_globs=["tests/test_predicates/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_passes, assert True) and negative case (test_*_fails, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Predicates filter matches; untested predicates can silently suppress real violations or let false ones through.",
    ),
    Rule(
        id="combinator-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_combinators/*.py"],
        exclude_globs=["tests/test_combinators/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_matches, assert on match list) and negative case (test_*_no_match, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Combinators compose matcher logic; untested combinators can invert or short-circuit the intended logic.",
    ),
    Rule(
        id="extractor-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_extractors/*.py"],
        exclude_globs=["tests/test_extractors/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_extracts, assert key in set) and negative case (test_*_absent, assert key not in set), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Extractors are pure string transforms; untested extractors silently break key extraction.",
    ),
    Rule(
        id="predicate-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/predicates/*.py"],
        exclude_globs=["enforcer/predicates/__init__.py"],
        message="Predicate class at {file}:{line} docstring missing 'What:' or 'Basis:' section.",
        fix_instruction="Add 'What: <what it passes>' and 'Basis: <RAW|AST_PY|AST_TS|AST_CSS>' lines to the class docstring.",
        diff_only=True,
        rationale="Predicates filter matches; structured docstrings explain what they pass and why.",
    ),
    Rule(
        id="combinator-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/combinators/*.py"],
        exclude_globs=["enforcer/combinators/__init__.py"],
        message="Combinator class at {file}:{line} docstring missing 'What:' section.",
        fix_instruction="Add 'What: <what it composes>' to the class docstring.",
        diff_only=True,
        rationale="Combinators compose matcher logic; structured docstrings explain the composition.",
    ),
    Rule(
        id="extractor-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/extractors/*.py"],
        exclude_globs=["enforcer/extractors/__init__.py"],
        message="Extractor class at {file}:{line} docstring missing 'What:' section.",
        fix_instruction="Add 'What: <what it extracts>' to the class docstring.",
        diff_only=True,
        rationale="Extractors are pure transforms; structured docstrings explain what they extract.",
    ),
]
```

- [ ] **Step 3: Create `enforcer_config/arch_rules.py`**

```python
"""Architecture rules: layer dependencies, import direction, canonical imports, config hygiene."""
from enforcer import Rule, Severity
from enforcer.matchers import (
    ArchitectureMatcher,
    ImportMatcher,
    CanonicalImportMatcher,
    DuplicateRuleIdMatcher,
    TypeHintMatcher,
)

ARCH_RULES = [
    Rule(
        id="arch-layer-deps",
        severity=Severity.ERROR,
        matchers=[ArchitectureMatcher(
            layers={
                "types":      ["enforcer/types.py"],
                "rule":       ["enforcer/rule.py"],
                "core":       ["enforcer/runner.py", "enforcer/context.py",
                               "enforcer/config.py", "enforcer/check_runner.py"],
                "matchers":   ["enforcer/matchers/**/*.py"],
                "predicates": ["enforcer/predicates/**/*.py"],
                "combinators":["enforcer/combinators/**/*.py"],
                "extractors": ["enforcer/extractors/**/*.py"],
                "parsers":    ["enforcer/parsers/**/*.py"],
                "io":         ["enforcer/cli.py", "enforcer/mcp_server.py",
                               "enforcer/reporter.py", "enforcer/docs.py",
                               "enforcer/explain.py", "enforcer/fix.py",
                               "enforcer/ignore.py"],
            },
            allowed_edges=[
                ("matchers", "types"),
                ("matchers", "parsers"),
                ("matchers", "extractors"),
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
                ("rule", "types"),
                ("rule", "combinators"),
            ],
            forbid_implicit=True,
        )],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/__init__.py"],
        diff_only=False,
        message="Layer violation: {matched_value} at {file}:{line}",
        fix_instruction="Move shared logic down to a lower layer, or add the edge to allowed_edges if intentional.",
        rationale="Importing upward creates circular deps and prevents isolated testing. Layers: types < rule/parsers/matchers/predicates/combinators/extractors < core < io.",
    ),
    Rule(
        id="no-private-cross-import",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.\S+\s+import\s+_\w+"])],
        file_globs=["enforcer/**/*.py"],
        message="Private import at {file}:{line}: importing _-prefixed names from other modules breaks encapsulation.",
        fix_instruction="Make the imported symbol public (remove _ prefix) or move the shared logic to a common module.",
        diff_only=True,
        rationale="Importing private symbols creates hidden coupling. If a module needs a _-prefixed name, it either belongs in a shared module or should be made public.",
    ),
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
    Rule(
        id="matchers-no-import-runner-cli",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[
            r"from\s+enforcer\.runner\s+import",
            r"from\s+enforcer\.cli\s+import",
            r"from\s+enforcer\.mcp_server\s+import",
            r"from\s+enforcer\.reporter\s+import",
            r"from\s+enforcer\.fix\s+import",
            r"from\s+enforcer\.docs\s+import",
            r"from\s+enforcer\.explain\s+import",
            r"from\s+enforcer\.config\s+import",
        ])],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py"],
        message="Import layer violation at {file}:{line}: matchers must not import from runner/cli/mcp_server/reporter/fix/docs/explain/config.",
        fix_instruction="Move the shared logic down to types.py, a new low-level module, or pass the dependency as a parameter.",
        diff_only=True,
        rationale="Matchers are low-level building blocks. If they import from higher layers (runner, cli), they become impossible to reuse in isolation or test without pulling the entire stack.",
    ),
    Rule(
        id="rule-no-import-up",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.runner\s+import", r"from\s+enforcer\.cli\s+import", r"from\s+enforcer\.mcp_server\s+import", r"from\s+enforcer\.reporter\s+import", r"from\s+enforcer\.fix\s+import", r"from\s+enforcer\.docs\s+import", r"from\s+enforcer\.explain\s+import", r"from\s+enforcer\.config\s+import"])],
        file_globs=["enforcer/rule.py"],
        message="Import layer violation at {file}:{line}: rule.py must not import from runner/cli/mcp_server/reporter/fix/docs/explain/config.",
        fix_instruction="Move the shared logic down to types.py or a new low-level module.",
        diff_only=True,
        rationale="rule.py defines Rule — the core unit of composition. Importing from runner or cli creates a circular dependency and prevents isolated testing.",
    ),
    Rule(
        id="runner-no-import-cli",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.cli\s+import", r"from\s+enforcer\.mcp_server\s+import"])],
        file_globs=["enforcer/runner.py"],
        message="Import layer violation at {file}:{line}: runner.py must not import from cli or mcp_server.",
        fix_instruction="Move the shared logic to a mid-level module that both runner and cli can import.",
        diff_only=True,
        rationale="runner.py applies rules to files. Importing from cli or mcp_server (entrypoints) creates a circular dependency and prevents reuse.",
    ),
    Rule(
        id="no-duplicate-rule-ids",
        severity=Severity.ERROR,
        matchers=[DuplicateRuleIdMatcher()],
        file_globs=["enforcer_config/__init__.py"],
        message="Duplicate Rule id '{matched_value}' in config. Each id must be unique.",
        fix_instruction="Rename one of the duplicate rules to a unique id.",
        rationale="Duplicate rule IDs silently shadow each other — one rule's config overwrites the other's in any id-keyed lookup.",
    ),
    Rule(
        id="public-function-return-type",
        severity=Severity.ERROR,
        matchers=[TypeHintMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py"],
        message="Function '{matched_value}' at {file}:{line} missing return type annotation.",
        fix_instruction="Add `-> ReturnType` to the function signature.",
        diff_only=True,
        rationale="Return type annotations document the contract and enable static analysis. Without them, callers must read the implementation to know what a function returns.",
    ),
]
```

- [ ] **Step 4: Create `enforcer_config/style_rules.py`**

Note: `config-size-cap` rule is **removed** (obsolete after split). `file-max-lines` exemption for `enforcer_config.py` is **removed**.

```python
"""Style rules: nesting, interface, file length, function complexity, imports, docstrings."""
from enforcer import Rule, Severity
from enforcer.matchers import (
    FunctionComplexityMatcher,
    InterfaceMatcher,
    LineCountMatcher,
    ImportMatcher,
    RegexMatcher,
    DocstringMatcher,
)

STYLE_RULES = [
    Rule(
        id="max-nesting-depth",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="nesting", max_value=3)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has nesting depth {matched_value} (max 3). Flatten with early returns or extract helpers.",
        fix_instruction="Extract nested logic into helper functions or use early returns/guard clauses.",
        diff_only=True,
        rationale="Deep nesting is hard to read, test, and maintain. Guard clauses and extraction keep functions flat and scannable.",
    ),
    Rule(
        id="class-needs-interface",
        severity=Severity.ERROR,
        matchers=[InterfaceMatcher(min_methods=4)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Class '{matched_value}' at {file}:{line} has >=4 methods but no base class. Inherit from Protocol/ABC or a base class.",
        fix_instruction="Add a base class (Protocol, ABC, or domain base) to the class definition.",
        diff_only=True,
        rationale="Classes with many methods and no interface are hard to mock, test in isolation, and substitute. An interface enables polymorphism and dependency injection.",
    ),
    Rule(
        id="file-max-lines",
        severity=Severity.ERROR,
        matchers=[LineCountMatcher(max_lines=400)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="File {file} has {matched_value} lines (max 400). Split into modules.",
        fix_instruction="Extract cohesive functionality into a new module or sub-package.",
        diff_only=True,
        rationale="Files over 400 lines do too much and are hard to navigate. Splitting into focused modules improves readability and testability.",
    ),
    Rule(
        id="function-max-lines",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="lines", max_value=75)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has {matched_value} lines (max 75). Split or extract.",
        fix_instruction="Extract sub-functions or move logic to a helper module.",
        diff_only=True,
        rationale="Long functions do too much and are hard to test, read, and review. Splitting forces single-responsibility and improves testability.",
    ),
    Rule(
        id="function-max-params",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="params", max_value=5)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has {matched_value} parameters (max 5). Group into a dataclass.",
        fix_instruction="Group related parameters into a dataclass and pass as single arg.",
        diff_only=True,
        rationale="More than 5 params signals the function does too much; group into a dataclass to make the boundary explicit and the call site readable.",
    ),
    Rule(
        id="cyclomatic-complexity",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="cyclomatic", max_value=10)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has cyclomatic complexity {matched_value} (max 10). Reduce branching.",
        fix_instruction="Extract branches into helper functions or use early returns.",
        diff_only=True,
        rationale="High cyclomatic complexity means too many branches — hard to reason about, test, and maintain. Extract branches into helpers or use early returns.",
    ),
    Rule(
        id="no-wildcard-imports",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"import\s+\*", r"from\s+\S+\s+import\s+\*"])],
        file_globs=["enforcer/**/*.py"],
        message="Wildcard import at {file}:{line}. Use explicit imports.",
        fix_instruction="Replace `from X import *` with explicit symbol imports.",
        diff_only=True,
        rationale="Wildcard imports pollute the namespace and hide dependencies. Explicit imports make it clear where symbols come from and avoid name collisions.",
    ),
    Rule(
        id="todo-needs-owner",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#\s*(TODO|FIXME|HACK|XXX)\b(?!\s*\(@)")],
        file_globs=["enforcer/**/*.py"],
        message="TODO/FIXME without owner at {file}:{line}. Use '# TODO(@name): …' or remove.",
        fix_instruction="Add owner reference or delete the TODO and address now.",
        diff_only=True,
        rationale="TODOs without owners never get done. An owner reference makes responsibility explicit and enables grepping for open work.",
    ),
    Rule(
        id="docstring-public",
        severity=Severity.ERROR,
        matchers=[DocstringMatcher()],
        file_globs=["enforcer/**/*.py"],
        message="Function '{matched_value}' at {file}:{line} missing docstring. Public functions must be documented.",
        fix_instruction='Add a docstring: """<one-line description>."""',
        diff_only=True,
        rationale="Public functions are the API surface. Without docstrings, users (and agents) must read the implementation to understand intent — that's a failure of the contract.",
    ),
]
```

- [ ] **Step 5: Create `enforcer_config/hygiene_rules.py`**

Note: `constants-upper-case` and `no-magic-numbers` exemptions for `enforcer_config.py` are **removed**.

```python
"""Hygiene rules: naming, side effects, secrets, debug code, scratch files."""
from enforcer import Rule, Severity
from enforcer.matchers import (
    AllSortedMatcher,
    NoModuleSideEffectsMatcher,
    ConstantNamingMatcher,
    MagicNumberMatcher,
    RegexMatcher,
    NamingConventionMatcher,
    AlwaysMatcher,
)

HYGIENE_RULES = [
    Rule(
        id="all-sorted",
        severity=Severity.ERROR,
        matchers=[AllSortedMatcher()],
        file_globs=["enforcer/**/*.py"],
        message="__all__ at {file}:{line} is not alphabetically sorted.",
        fix_instruction="Sort the __all__ entries alphabetically.",
        diff_only=True,
        rationale="Unsorted __all__ lists cause diff noise and make it hard to find exports. Alphabetical order is deterministic and scannable.",
    ),
    Rule(
        id="no-module-side-effects",
        severity=Severity.ERROR,
        matchers=[NoModuleSideEffectsMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py"],
        message="Module-level side effect at {file}:{line}: '{matched_value}' statement runs at import time.",
        fix_instruction="Move the side effect into a function or class method. Import-time execution breaks isolation and makes testing unpredictable.",
        diff_only=True,
        rationale="Module-level side effects (calls, loops, prints) run at import time, breaking isolation, making tests unpredictable, and causing import-order bugs.",
    ),
    Rule(
        id="constants-upper-case",
        severity=Severity.ERROR,
        matchers=[ConstantNamingMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py"],
        message="Module-level constant '{matched_value}' at {file}:{line} must be UPPER_CASE.",
        fix_instruction="Rename to UPPER_CASE or prefix with _ if private.",
        diff_only=True,
        rationale="UPPER_CASE constants are the Python convention (PEP 8). They distinguish compile-time-fixed values from mutable variables at a glance.",
    ),
    Rule(
        id="no-magic-numbers",
        severity=Severity.ERROR,
        matchers=[MagicNumberMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py", "enforcer/types.py"],
        message="Magic number {matched_value} at {file}:{line}. Extract to a named constant.",
        fix_instruction="Assign to an UPPER_CASE constant: `MAX_VALUE = 42` then use `MAX_VALUE`.",
        diff_only=True,
        rationale="Magic numbers are unexplained literals. Without a name, their meaning is opaque. A named constant documents intent and centralizes change.",
    ),
    Rule(
        id="function-snake-case",
        severity=Severity.ERROR,
        matchers=[NamingConventionMatcher(
            declaration_types=["function_definition"],
            pattern=r"^[a-z_][a-z0-9_]*$",
        )],
        file_globs=["enforcer/**/*.py"],
        message="Function '{matched_value}' at {file}:{line} must be snake_case",
        fix_instruction="Rename to snake_case.",
        diff_only=True,
        rationale="snake_case is the Python convention (PEP 8). Deviating creates inconsistency that makes code harder to scan.",
    ),
    Rule(
        id="class-capwords",
        severity=Severity.ERROR,
        matchers=[NamingConventionMatcher(
            declaration_types=["class_definition"],
            pattern=r"^[A-Z][a-zA-Z0-9]*$",
        )],
        file_globs=["enforcer/**/*.py"],
        message="Class '{matched_value}' at {file}:{line} must be CapWords (PascalCase)",
        fix_instruction="Rename to CapWords.",
        diff_only=True,
        rationale="CapWords (PascalCase) is the Python convention for classes (PEP 8). Distinguishes types from functions at a glance.",
    ),
    Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found in library code at {file}:{line}. Use sys.stderr.write or structlog.",
        fix_instruction="Replace print() with sys.stderr.write(...).",
        rationale="print() writes to stdout, which is reserved for machine-readable output in CLI tools. Mixing human prose into stdout breaks piping and scripting. sys.stderr is the correct channel for human-facing diagnostics.",
    ),
    Rule(
        id="no-bare-except",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*except\s*:")],
        file_globs=["enforcer/**/*.py"],
        message="Bare except: at {file}:{line}. Use except Exception or more specific.",
        fix_instruction="Change to `except Exception:` or a more specific exception.",
        rationale="Bare except catches SystemExit and KeyboardInterrupt, masking intentional exits and making debugging impossible.",
    ),
    Rule(
        id="no-secrets",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]", redact=True)],
        file_globs=["**/*.py"],
        exclude_globs=["**/test*", "**/*test*"],
        message="Possible hardcoded secret at {file}:{line}. Use env var.",
        fix_instruction="Move to env var or secrets manager.",
        rationale="Hardcoded secrets ship to the repo and can't be rotated without a commit. Env vars separate config from code and keep secrets out of version control.",
    ),
    Rule(
        id="no-debug-code",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*(breakpoint\s*\(\s*\)|import\s+pdb|pdb\.set_trace\s*\()")],
        file_globs=["**/*.py"],
        exclude_globs=["**/test*", "**/*test*"],
        message="Debug code at {file}:{line}. Remove before commit.",
        fix_instruction="Remove breakpoint()/pdb.set_trace() or wrap in `if DEBUG:` guard.",
        rationale="Debug code left in production halts execution and blocks CI. A single forgotten breakpoint can page someone at 3am.",
    ),
    Rule(
        id="no-bare-type-ignore",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#\s*type:\s*ignore\s*$")],
        file_globs=["**/*.py"],
        message="Bare `# type: ignore` at {file}:{line} silences errors without explanation.",
        fix_instruction="Add a reason: `# type: ignore[<error-code>]  # <why>`",
        diff_only=True,
        rationale="Bare `# type: ignore` hides real type errors and spreads — future readers can't tell if the ignore is still needed. A reason forces the author to justify the suppression.",
    ),
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
]
```

- [ ] **Step 6: Create `enforcer_config/self_enforce.py`**

```python
"""Self-enforcement rules: reminders, CONVENTIONS.md sync, LLM checks, facade pattern."""
from enforcer import Rule, Severity, RuleType, LLMConsequence
from enforcer.matchers import (
    LineCountMatcher,
    LLMMatcher,
    DocSyncMatcher,
    AlwaysMatcher,
    FacadeExistsMatcher,
    FacadeExposesInterfaceMatcher,
)

SELF_ENFORCE_RULES = [
    Rule(
        id="readme-max-lines",
        severity=Severity.ERROR,
        matchers=[LineCountMatcher(max_lines=300)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 300). LLM analyzed what doesn't belong.",
        fix_instruction="Remove or trim the sections flagged by the LLM response below.",
        llm_consequence=LLMConsequence(
            prompt="You are reviewing a README.md that exceeds 300 lines. Identify the specific sections that don't belong in a README and make it too long. For each section, explain why it should be removed or trimmed. Be concrete — reference section headings and line ranges. Common bloat: full install logs, API reference dumps, changelogs, verbose examples, duplicated content.",
            timeout=300,
        ),
        rationale="A README over 300 lines is too long for a landing doc. Bloat hides the getting-started path; details belong in docs/.",
    ),
    Rule(
        id="commit-msg-aligns-with-changes",
        severity=Severity.WARN,
        matchers=[LLMMatcher(
            prompt="Given the commit message and the modified file list, does the message accurately describe these changes? Lenient — sanity check only, not a full audit.",
            timeout=30,
        )],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Commit message may not align with changes. LLM: {matched_value}",
        fix_instruction="Rewrite commit message to describe the actual changes.",
        rationale="A commit message that doesn't describe the actual changes misleads future archaeologists using git log/blame. The LLM sanity check catches gross mismatches.",
    ),
    Rule(
        id="facade-exists",
        severity=Severity.WARN,
        matchers=[FacadeExistsMatcher(
            source_glob="enforcer/*",
            facade="__init__.py",
            workspace=".",
        )],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/__init__.py"],
        diff_only=False,
        message="Submodule {file} has no facade (__init__.py)",
        fix_instruction="Create enforcer/{file}/__init__.py re-exporting the public API.",
        rationale="Every submodule should have a facade (__init__.py) that re-exports its public API. This enables clean imports and hides internal structure.",
    ),
    Rule(
        id="facade-exposes-interface",
        severity=Severity.WARN,
        matchers=[FacadeExposesInterfaceMatcher()],
        file_globs=["enforcer/*/__init__.py"],
        diff_only=False,
        message="Facade {file} exposes no interface (Protocol/ABC or __all__)",
        fix_instruction="Add a Protocol/ABC class or __all__ re-export to the facade.",
        rationale="Facades should expose a public interface (Protocol/ABC) or at minimum an __all__ re-export. This documents the contract and enables dependency injection.",
    ),
    Rule(
        id="verify-types-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="types.py changed")],
        file_globs=["enforcer/types.py"],
        message="Core types changed in {file}. Every matcher/predicate/combinator depends on these. Run full test suite: pytest --tb=short -q",
        fix_instruction="Verify: pytest passes, no matcher breaks on new types.py.",
        diff_only=True,
        rationale="types.py is load-bearing — every matcher, predicate, and combinator depends on it. Changes here can break the entire rule engine silently.",
    ),
    Rule(
        id="verify-rule-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="rule.py changed")],
        file_globs=["enforcer/rule.py"],
        message="Rule/glob matching changed in {file}. _glob_match and Rule.check() affect every rule. Run: pytest tests/test_rule.py tests/test_runner.py",
        fix_instruction="Verify: glob matching works for ** patterns, Rule.check() stamps metadata correctly.",
        diff_only=True,
        rationale="rule.py contains _glob_match and Rule.check() — every rule flows through it. Changes here affect glob matching and metadata stamping for all rules.",
    ),
    Rule(
        id="verify-runner-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="runner.py changed")],
        file_globs=["enforcer/runner.py"],
        message="Runner changed in {file}. Cross-file finalizers and severity filtering affect all rules. Run: pytest tests/test_runner.py tests/test_metadata_rules.py",
        fix_instruction="Verify: run_cross_file_finalizers works, severity filtering correct, LLM consequences fire.",
        diff_only=True,
        rationale="runner.py drives severity filtering, LLM consequence execution, and cross-file finalizers. Changes here can silently change which rules fire.",
    ),
    Rule(
        id="verify-context-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="context.py changed")],
        file_globs=["enforcer/context.py"],
        message="FileContextBuilder changed in {file}. Parse-once cache drives all AST matchers. Run: pytest tests/test_context.py tests/test_parse_once.py",
        fix_instruction="Verify: AST populated lazily, cache hits don't reparse, needs_for_file aggregates correctly.",
        diff_only=True,
        rationale="context.py owns the parse-once cache. A broken cache means every AST matcher re-parses or gets stale ASTs.",
    ),
    Rule(
        id="verify-config-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="config.py changed")],
        file_globs=["enforcer/config.py"],
        message="Config loader changed in {file}. load_config executes enforcer_config as module. Run: pytest tests/test_config.py",
        fix_instruction="Verify: RULES/WORKSPACE/SEVERITY_ACTIONS/LLM_CONFIG extracted correctly, defaults work.",
        diff_only=True,
        rationale="config.py executes enforcer_config as a module. Changes here affect how every rule is loaded.",
    ),
    Rule(
        id="verify-parser-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="parser changed")],
        file_globs=["enforcer/parsers/*.py"],
        message="Parser changed in {file}. Tree-sitter parse affects all AST matchers. Run: pytest tests/test_parsers.py tests/test_parse_once.py",
        fix_instruction="Verify: Python/TS/CSS ASTs parse correctly, language_for_path maps extensions right.",
        diff_only=True,
        rationale="The tree-sitter parser feeds all AST matchers. Changes here can silently break AST detection for Python, TS, or CSS.",
    ),
    Rule(
        id="conventions-md-stale",
        severity=Severity.ERROR,
        matchers=[DocSyncMatcher(doc_path="CONVENTIONS.md")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="CONVENTIONS.md is stale or missing. Regenerate after changing rules.",
        fix_instruction="Run: enforcer sync-doc",
        rationale="A stale conventions doc misleads agents — they follow rules that no longer match the actual config. The doc must be regenerated whenever RULES changes, and direct edits to CONVENTIONS.md must not drift it from the config.",
    ),
]
```

- [ ] **Step 7: Create `enforcer_config/__init__.py`**

```python
"""Self-enforcement config for pre-commit-agent-enforcer (package form).

Composes rules from sub-config modules. Each sub-config owns a section;
this file imports and concatenates them into RULES.

Severity philosophy:
  ERROR — style/correctness violations. Always blocks. Must fix before commit.
  WARN  — critical-component reminders. Blocks unless --confirm-read-warnings.
          Fires when you touch files that have broad blast radius. The reminder
          tells you what to verify before acknowledging.

Setup (one-time):
  enforcer install --force
  export ENFORCER_CONFIG=enforcer_config
"""
from enforcer import LLMConfig
from enforcer_config.git_rules import GIT_RULES
from enforcer_config.test_rules import TEST_RULES
from enforcer_config.arch_rules import ARCH_RULES
from enforcer_config.style_rules import STYLE_RULES
from enforcer_config.hygiene_rules import HYGIENE_RULES
from enforcer_config.self_enforce import SELF_ENFORCE_RULES

WORKSPACE = "."

RULES = [
    *GIT_RULES,
    *TEST_RULES,
    *ARCH_RULES,
    *STYLE_RULES,
    *HYGIENE_RULES,
    *SELF_ENFORCE_RULES,
]

SEVERITY_ACTIONS = {
    "ERROR": "block",
    "WARN": "block_warn",
    "INFO": "hint",
}

LLM_CONFIG = LLMConfig(
    default_provider="custom",
    default_model="zai-org/GLM-5.1-FP8",
    concurrency=3,
    timeout=45,
)
```

- [ ] **Step 8: Verify package loads correctly**

Run: `python -c "from enforcer_config import RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG; print(f'{len(RULES)} rules, workspace={WORKSPACE}')"`
Expected: `44 rules, workspace=.` (was 45, minus 1 for removed `config-size-cap`).

- [ ] **Step 9: Verify enforcer self-check passes on new package files**

Run: `python -m enforcer.cli check --paths enforcer_config/`
Expected: No issues found (or only issues that will be resolved by deleting the old file in Task 5). If `constants-upper-case` or `no-magic-numbers` fire, see the spec's fallback: add targeted exemptions for the specific sub-config file.

- [ ] **Step 10: Commit**

```bash
git add enforcer_config/
git commit -s -m "feat(config): split enforcer_config.py into package

866-line monolith → 7-file package (each under 200 lines). Each
sub-config owns a section: git, test, arch, style, hygiene, self-enforce.
__init__.py composes RULES = [*GIT_RULES, *TEST_RULES, ...].

Removed config-size-cap rule (obsolete after split). Removed
enforcer_config.py exemptions from file-max-lines, constants-upper-case,
no-magic-numbers."
```

---

## Task 4: Switch defaults and update tests

**Files:**
- Modify: `enforcer/cli.py` (4 `--config` defaults)
- Modify: `enforcer/mcp_server.py` (1 default)
- Modify: `tests/test_explain.py:360,370`
- Modify: `tests/test_matchers/test_doc_sync.py:31`
- Modify: `tests/test_cli_refactor.py:64`
- Delete: `enforcer_config.py`

- [ ] **Step 1: Update CLI defaults**

In `enforcer/cli.py`, replace all 4 occurrences of `default="enforcer_config.py"` with `default="enforcer_config"`:

Line 45:
```python
@click.option("--config", "config_path", default="enforcer_config", help="Path to enforcer config (file or package)")
```

Line 125:
```python
@click.option("--config", "config_path", default="enforcer_config")
```

Line 145:
```python
@click.option("--config", "config_path", default="enforcer_config")
```

Line 185:
```python
@click.option("--config", "config_path", default="enforcer_config")
```

- [ ] **Step 2: Update MCP server default**

In `enforcer/mcp_server.py` line 20:
```python
    return os.environ.get("ENFORCER_CONFIG", "enforcer_config")
```

- [ ] **Step 3: Update test_explain.py**

In `tests/test_explain.py`, replace `load_config("enforcer_config.py")` with `load_config("enforcer_config")` at lines 360 and 370.

- [ ] **Step 4: Update test_doc_sync.py**

In `tests/test_matchers/test_doc_sync.py` line 31, replace `load_config("enforcer_config.py")` with `load_config("enforcer_config")`.

Also update the fixture at line 20 — the `(tmp_path / "enforcer_config.py").write_text(rules_src)` creates a temp file. This still works because `load_config()` handles `.py` file paths. But the `load_config("enforcer_config.py")` call on line 31 needs to point to the temp file. Check the fixture: it changes cwd to `tmp_path` then loads `enforcer_config.py`. This still works — `load_config("enforcer_config.py")` ends in `.py` so it uses `spec_from_file_location`. No change needed to the fixture, only to the explicit `load_config("enforcer_config")` call if it references the real repo config.

**Actually** — re-read the test. Line 31 calls `load_config("enforcer_config.py")` after writing to `tmp_path / "enforcer_config.py"`. Since `load_config` still handles `.py` paths, this works unchanged. **Do not modify this test.** It writes its own temp config file and loads it by path.

- [ ] **Step 5: Update test_cli_refactor.py**

In `tests/test_cli_refactor.py` line 64, the test writes `enforcer_config.py` to cwd and relies on the default `--config`. After the default changes to `enforcer_config` (package), this test breaks because the default now loads the package, not the temp file.

Fix: pass `--config enforcer_config.py` explicitly in the CLI invocation. Read the test to find the `runner.invoke(cli, [...])` call and add `--config enforcer_config.py`.

```bash
# Read the test first to find the exact invocation
```

The test at line 64 writes the file and likely invokes the CLI without `--config`. Add `"--config", "enforcer_config.py"` to the args list of the `runner.invoke` call.

- [ ] **Step 6: Delete `enforcer_config.py`**

```bash
git rm enforcer_config.py
```

- [ ] **Step 7: Run tests**

Run: `pytest --tb=short -q`
Expected: All pass. If any test fails because it references `enforcer_config.py` as the real repo config, update it to use `enforcer_config` (package).

- [ ] **Step 8: Run enforcer self-check**

Run: `python -m enforcer.cli check --all`
Expected: No issues found.

- [ ] **Step 9: Commit**

```bash
git add enforcer/cli.py enforcer/mcp_server.py tests/test_explain.py tests/test_cli_refactor.py
git rm enforcer_config.py
git commit -s -m "refactor(config): switch defaults to enforcer_config package

CLI and MCP server default --config from enforcer_config.py to
enforcer_config (package). Delete enforcer_config.py. Update tests
that loaded the real repo config by filename."
```

---

## Task 5: Regenerate CONVENTIONS.md and final verification

**Files:**
- Modify: `CONVENTIONS.md`

- [ ] **Step 1: Regenerate CONVENTIONS.md**

Run: `python -m enforcer.cli sync-doc`
Expected: `CONVENTIONS.md` updated with new rule list (44 rules, no `config-size-cap`).

- [ ] **Step 2: Verify enforcer self-check**

Run: `python -m enforcer.cli check --all`
Expected: No issues found.

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 4: Verify file sizes**

Run: `wc -l enforcer_config/*.py`
Expected: Each file under 200 lines.

- [ ] **Step 5: Commit**

```bash
git add CONVENTIONS.md
git commit -s -m "docs: regenerate CONVENTIONS.md for config split

44 rules (was 45 — config-size-cap removed). Rules now live in
enforcer_config/ package."
```

---

## Self-Review

**1. Spec coverage:**
- Config split into package: Task 3 ✓
- `load_config()` updated for packages: Task 2 ✓
- CLI/MCP defaults updated: Task 4 ✓
- `config-size-cap` removed: Task 3 (style_rules.py omits it) ✓
- `file-max-lines` exemption removed: Task 3 (style_rules.py) ✓
- `constants-upper-case` exemption removed: Task 3 (hygiene_rules.py) ✓
- `no-magic-numbers` exemption removed: Task 3 (hygiene_rules.py) ✓
- `no-duplicate-rule-ids` path updated: Task 3 (arch_rules.py → `enforcer_config/__init__.py`) ✓
- `CanonicalImportMatcher` fix: Task 1 ✓
- `CONVENTIONS.md` regenerated: Task 5 ✓
- Old `enforcer_config.py` deleted: Task 4 ✓
- Tests updated: Task 4 ✓

**2. Placeholder scan:** No TBD/TODO. All code shown. ✓

**3. Type consistency:** `_non_canonical_names` returns `list[str]`, `_build_match` takes `name: str, module: str`. `GIT_RULES`, `TEST_RULES`, etc. all `list[Rule]`. `RULES` composes via `*` unpacking. ✓
