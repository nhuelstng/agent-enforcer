# Tier 2 Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-fix capability, naming-convention enforcement, branch/commit-message rules, and enhanced AST predicates to the enforcer — making it actionable (fix, not just flag) and covering convention classes beyond file contents.

**Architecture:** Auto-fix uses a `FixProvider` protocol — matchers optionally implement `fix(file_ctx, match) -> str` returning patched source. CLI `--fix` writes patches in-place. NamingConventionMatcher extends the AST-walker pattern (like ImportMatcher). Branch/commit rules are a new `RuleType` ("content" vs "metadata") dispatched by the runner. Enhanced predicates are new predicate classes composing with existing ones.

**Tech Stack:** Python 3.13, tree-sitter (TS/Python/CSS), click, pytest, pathlib

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `enforcer/types.py` | Modify | Add `RuleType` enum (CONTENT, METADATA), add `fix_applied: str` field to `Match` |
| `enforcer/matchers/naming_convention.py` | Create | Walk AST for class/function/variable declarations, check name against regex/style |
| `enforcer/matchers/branch_name.py` | Create | Check current git branch name against regex pattern |
| `enforcer/matchers/commit_message.py` | Create | Check commit message against regex/conventional-commits format |
| `enforcer/predicates/ast.py` | Create | `HasDecoratorPredicate`, `NodeNamePredicate` |
| `enforcer/fix.py` | Create | `FixProvider` protocol, `apply_fixes()` — orchestrates fix calls per file |
| `enforcer/rule.py` | Modify | Add `rule_type: RuleType` field, add `fix` field (optional `FixProvider`) |
| `enforcer/runner.py` | Modify | Dispatch metadata rules separately from content rules |
| `enforcer/cli.py` | Modify | Add `--fix` flag, `--branch` flag (for non-commit contexts), metadata rule execution |
| `enforcer/matchers/__init__.py` | Modify | Export new matchers |
| `enforcer/predicates/__init__.py` | Modify | Export new predicates |
| `enforcer/__init__.py` | Modify | Export `RuleType` |
| `tests/test_matchers/test_naming_convention.py` | Create | Tests for naming convention matcher |
| `tests/test_matchers/test_branch_name.py` | Create | Tests for branch name matcher |
| `tests/test_matchers/test_commit_message.py` | Create | Tests for commit message matcher |
| `tests/test_predicates/test_ast_predicates.py` | Create | Tests for AST predicates |
| `tests/test_fix.py` | Create | Tests for auto-fix flow |
| `tests/test_metadata_rules.py` | Create | Tests for branch/commit rule execution |

---

## Task 1: `RuleType` enum and metadata rule dispatch

**Files:**
- Modify: `enforcer/types.py`
- Modify: `enforcer/rule.py:34-48`
- Modify: `enforcer/runner.py:24-36`
- Test: `tests/test_metadata_rules.py`

**Context:** Branch name and commit message rules don't operate on file contents — they operate on git metadata. The runner needs to dispatch them separately. `RuleType.CONTENT` rules run per-file (existing behavior). `RuleType.METADATA` rules run once, against the repo/commit.

- [ ] **Step 1: Write failing test**

```python
# tests/test_metadata_rules.py
"""Tests for metadata rule dispatch (branch/commit rules)."""
from enforcer.types import Severity, RuleType, Match
from enforcer.rule import Rule
from enforcer.matchers.always import AlwaysMatcher

def test_rule_has_rule_type_field():
    """Rule should have a rule_type field defaulting to CONTENT."""
    r = Rule(id="x", severity=Severity.WARN, matchers=[AlwaysMatcher()], file_globs=["*"])
    assert r.rule_type == RuleType.CONTENT

def test_rule_can_be_metadata_type():
    """Rule should accept rule_type=RuleType.METADATA."""
    r = Rule(id="branch", severity=Severity.ERROR, matchers=[AlwaysMatcher()],
             file_globs=["*"], rule_type=RuleType.METADATA)
    assert r.rule_type == RuleType.METADATA

def test_runner_separates_metadata_rules():
    """RuleRunner should separate metadata rules from content rules."""
    from enforcer.runner import RuleRunner
    content_rule = Rule(id="c", severity=Severity.WARN, matchers=[AlwaysMatcher()], file_globs=["*.py"])
    meta_rule = Rule(id="m", severity=Severity.ERROR, matchers=[AlwaysMatcher()],
                     file_globs=["*"], rule_type=RuleType.METADATA)
    runner = RuleRunner([content_rule, meta_rule], workspace=".", no_llm=True)
    assert content_rule in runner.content_rules
    assert meta_rule in runner.metadata_rules

def test_runner_runs_metadata_rules_once():
    """Runner should run metadata rules once, not per-file."""
    from enforcer.runner import RuleRunner
    from enforcer.types import FileContext
    from enforcer.matchers.regex import RegexMatcher
    import subprocess, tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        os.makedirs(os.path.join(tmpdir, ".git/refs/heads"), exist_ok=True)
        Path(tmpdir, ".git/HEAD").write_text("ref: refs/heads/feature/test-123\n")
        Path(tmpdir, ".git/refs/heads/feature").mkdir(parents=True, exist_ok=True)
        Path(tmpdir, ".git/refs/heads/feature/test-123").write_text("0" * 40)

        meta_rule = Rule(
            id="branch-needs-ticket",
            severity=Severity.ERROR,
            matchers=[AlwaysMatcher(matched_value="bad branch")],
            file_globs=["*"],
            rule_type=RuleType.METADATA,
        )
        runner = RuleRunner([meta_rule], workspace=tmpdir, no_llm=True)
        ctx = FileContext(path="foo.py", raw="x = 1")
        matches = runner.run_rules_for_file(ctx, {})
        # Metadata rule should NOT fire during per-file run
        assert matches == []
        # Metadata rules fire via run_metadata_rules()
        meta_matches = runner.run_metadata_rules({})
        assert len(meta_matches) == 1
```

```python
# tests/test_metadata_rules.py (add to top)
from pathlib import Path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_metadata_rules.py -v`
Expected: FAIL — `RuleType` does not exist, `rule_type` field missing.

- [ ] **Step 3: Add `RuleType` to types.py**

In `enforcer/types.py`, add after `Needs`:

```python
class RuleType(Enum):
    """Whether a rule operates on file contents (per-file) or git metadata (once per run)."""
    CONTENT = "content"
    METADATA = "metadata"
```

- [ ] **Step 4: Add `rule_type` field to `Rule`**

In `enforcer/rule.py`, add field to the `Rule` dataclass:

```python
from enforcer.types import Severity, Match, FileContext, LLMConsequence, RuleType

@dataclass
class Rule:
    # ... existing fields ...
    diff_only: bool = False
    rule_type: RuleType = RuleType.CONTENT
```

- [ ] **Step 5: Update `RuleRunner` to separate and dispatch metadata rules**

In `enforcer/runner.py`:

```python
from enforcer.types import Severity, Match, FileContext, RuleType

class RuleRunner:
    def __init__(self, rules: list[Rule], workspace: str = ".",
                 no_llm: bool = False, min_severity: Severity = Severity.INFO,
                 llm_config: dict | None = None):
        self.rules = rules
        self.workspace = workspace
        self.min_severity = min_severity
        self.content_rules = [r for r in rules if r.rule_type == RuleType.CONTENT]
        self.metadata_rules = [r for r in rules if r.rule_type == RuleType.METADATA]
        llm_config = llm_config or {"concurrency": 5, "timeout": 30}
        self.llm_executor = LLMExecutor(
            concurrency=llm_config.get("concurrency", 5),
            timeout=llm_config.get("timeout", 30),
            enabled=not no_llm,
        )

    def run_rules_for_file(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        """Run all CONTENT rules against one file. Returns list of Match objects."""
        all_matches: list[Match] = []
        for rule in self.content_rules:
            if not self._file_matches(file_ctx.path, rule):
                continue
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            matches = rule.check(file_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, file_ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches

    def run_metadata_rules(self, shared_ctx: dict) -> list[Match]:
        """Run all METADATA rules once. Returns list of Match objects."""
        all_matches: list[Match] = []
        for rule in self.metadata_rules:
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            fake_ctx = FileContext(path=self.workspace, raw=None)
            matches = rule.check(fake_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, fake_ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches

    # keep _file_matches and run() unchanged
```

- [ ] **Step 6: Export `RuleType` from `enforcer/__init__.py`**

Add `RuleType` to the imports and `__all__` in `enforcer/__init__.py`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_metadata_rules.py -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All 211 existing tests pass (default `rule_type=CONTENT` is backward compatible).

- [ ] **Step 9: Commit**

```bash
git add enforcer/types.py enforcer/rule.py enforcer/runner.py enforcer/__init__.py tests/test_metadata_rules.py
git commit -m "feat: RuleType enum — separate content rules from metadata rules

CONTENT rules run per-file (existing behavior). METADATA rules run
once per check invocation, against git metadata (branch name, commit
message). Enables branch-name and commit-message convention rules."
```

---

## Task 2: `BranchNameMatcher` — enforce branch naming conventions

**Files:**
- Create: `enforcer/matchers/branch_name.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_branch_name.py`

**Context:** ASML and many teams enforce branch naming like `feature/ABC-123-description` or `fix/issue-456`. This matcher reads the current git branch and flags if it doesn't match a required pattern.

- [ ] **Step 1: Write failing test**

```python
# tests/test_matchers/test_branch_name.py
"""Tests for BranchNameMatcher: enforces branch naming conventions."""
import subprocess
import tempfile
from pathlib import Path
from enforcer.matchers.branch_name import BranchNameMatcher
from enforcer.types import FileContext

def _init_git_repo(tmpdir, branch_name="main"):
    subprocess.run(["git", "init", "-b", branch_name], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)
    if branch_name != "main":
        subprocess.run(["git", "branch", branch_name], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", branch_name], cwd=tmpdir, capture_output=True)

def test_branch_name_matches_pattern():
    """Should not flag when branch matches required pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "feature/ABC-123-add-login")
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_branch_name_does_not_match():
    """Should flag when branch doesn't match required pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "bad-branch-name")
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-")
        ctx = FileContext(path=tmpdir, raw=None)
        matches = matcher.find(ctx, {})
        assert len(matches) == 1
        assert "bad-branch-name" in matches[0].matched_value

def test_branch_name_allows_main():
    """Should allow main/master branches when listed in allow_branches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "main")
        matcher = BranchNameMatcher(pattern=r"^feature/", allow_branches=["main", "master"])
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_branch_name_detached_head():
    """Should not crash on detached HEAD state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "main")
        subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=tmpdir, capture_output=True)
        matcher = BranchNameMatcher(pattern=r"^feature/")
        ctx = FileContext(path=tmpdir, raw=None)
        # Should return empty (can't check branch in detached state) or a match
        result = matcher.find(ctx, {})
        assert isinstance(result, list)

def test_branch_name_not_a_git_repo():
    """Should not crash when workspace is not a git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        matcher = BranchNameMatcher(pattern=r"^feature/")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_branch_name.py -v`
Expected: FAIL — `BranchNameMatcher` does not exist.

- [ ] **Step 3: Implement `BranchNameMatcher`**

```python
# enforcer/matchers/branch_name.py
"""BranchNameMatcher: checks current git branch against a required pattern."""
from __future__ import annotations
import re
import subprocess
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs

@dataclass
class BranchNameMatcher:
    """Flags if the current git branch name doesn't match the required pattern.
    Set allow_branches to skip check for specific branches (main, master, develop)."""
    pattern: str
    allow_branches: list[str] = field(default_factory=lambda: ["main", "master", "develop"])
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self.workspace,
            )
            if result.returncode != 0:
                return []
            branch = result.stdout.strip()
        except Exception:
            return []

        if branch in self.allow_branches or branch == "HEAD":
            return []

        if self._compiled.search(branch):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=branch,
        )]
```

- [ ] **Step 4: Export from `__init__.py`**

In `enforcer/matchers/__init__.py`, add:

```python
from enforcer.matchers.branch_name import BranchNameMatcher
```

Add `"BranchNameMatcher"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_branch_name.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/matchers/branch_name.py enforcer/matchers/__init__.py tests/test_matchers/test_branch_name.py
git commit -m "feat: BranchNameMatcher — enforce branch naming conventions

Reads current git branch via 'git rev-parse --abbrev-ref HEAD'.
Flags if branch doesn't match required regex pattern.
Allows main/master/develop by default. Handles detached HEAD
and non-git directories gracefully."
```

---

## Task 3: `CommitMessageMatcher` — enforce commit message format

**Files:**
- Create: `enforcer/matchers/commit_message.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_commit_message.py`

**Context:** Conventional Commits (`feat:`, `fix:`, `docs:`, etc.) or ticket-prefix enforcement. Pre-commit hook has access to the commit message via `.git/COMMIT_EDITMSG` or the `--commit-msg` hook stage.

- [ ] **Step 1: Write failing test**

```python
# tests/test_matchers/test_commit_message.py
"""Tests for CommitMessageMatcher: enforces commit message format."""
import subprocess
import tempfile
from pathlib import Path
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.types import FileContext

def _init_git_with_commit_msg(tmpdir, msg):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    # Write commit message file
    Path(tmpdir, ".git/COMMIT_EDITMSG").write_text(msg)

def test_commit_message_matches_conventional_commits():
    """Should not flag a valid conventional commit message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: add login page\n\nCloses ABC-123")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_does_not_match():
    """Should flag a non-conventional commit message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "updated stuff")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+")
        ctx = FileContext(path=tmpdir, raw=None)
        matches = matcher.find(ctx, {})
        assert len(matches) == 1
        assert "updated stuff" in matches[0].matched_value

def test_commit_message_multiline():
    """Should check only the first line of a multi-line message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "fix: handle null\n\nBody text here\nMore body")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_no_msg_file():
    """Should not crash if .git/COMMIT_EDITMSG doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        matcher = CommitMessageMatcher(pattern=r"^feat:")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_custom_pattern():
    """Should support custom ticket-prefix patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "ABC-123: add feature")
        matcher = CommitMessageMatcher(pattern=r"^\w+-\d+:\s+.+")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_merge_commit_skipped():
    """Should skip merge commits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "Merge branch 'feature' into main")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+")
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_commit_message.py -v`
Expected: FAIL — `CommitMessageMatcher` does not exist.

- [ ] **Step 3: Implement `CommitMessageMatcher`**

```python
# enforcer/matchers/commit_message.py
"""CommitMessageMatcher: checks commit message against a required pattern."""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommitMessageMatcher:
    """Flags if the commit message (first line) doesn't match the required pattern.
    Reads from .git/COMMIT_EDITMSG. Skips merge commits."""
    pattern: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        msg_path = Path(self.workspace, ".git", "COMMIT_EDITMSG")
        if not msg_path.exists():
            return []
        try:
            content = msg_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        first_line = content.splitlines()[0] if content.splitlines() else ""

        if first_line.startswith("Merge"):
            return []

        if self._compiled.search(first_line):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=first_line,
        )]
```

- [ ] **Step 4: Export from `__init__.py`**

In `enforcer/matchers/__init__.py`, add:

```python
from enforcer.matchers.commit_message import CommitMessageMatcher
```

Add `"CommitMessageMatcher"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_commit_message.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/matchers/commit_message.py enforcer/matchers/__init__.py tests/test_matchers/test_commit_message.py
git commit -m "feat: CommitMessageMatcher — enforce commit message format

Reads .git/COMMIT_EDITMSG, checks first line against regex.
Supports Conventional Commits or ticket-prefix patterns.
Skips merge commits. Handles missing file gracefully."
```

---

## Task 4: `NamingConventionMatcher` — enforce class/function/variable naming

**Files:**
- Create: `enforcer/matchers/naming_convention.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_naming_convention.py`

**Context:** ASML requires PascalCase classes, camelCase TS functions, snake_case Python functions. This matcher walks AST declarations and checks names against a regex.

- [ ] **Step 1: Write failing test**

```python
# tests/test_matchers/test_naming_convention.py
"""Tests for NamingConventionMatcher: enforces naming conventions on declarations."""
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.types import FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def test_python_function_must_be_snake_case():
    """Should flag non-snake_case Python function names."""
    ctx = _make_ctx("def BadName():\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "BadName" in matches[0].matched_value

def test_python_function_snake_case_ok():
    """Should not flag snake_case Python function names."""
    ctx = _make_ctx("def good_name():\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    assert matcher.find(ctx) == []

def test_python_class_must_be_pascal_case():
    """Should flag non-PascalCase Python class names."""
    ctx = _make_ctx("class lower_case:\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["class_definition"],
        pattern=r"^[A-Z][a-zA-Z0-9]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "lower_case" in matches[0].matched_value

def test_typescript_method_camel_case():
    """Should flag non-camelCase TypeScript method names."""
    ctx = _make_ctx(
        "class Foo {\n  Bad_Method(): void {}\n}\n",
        lang=Needs.AST_TS,
    )
    matcher = NamingConventionMatcher(
        declaration_types=["method_definition"],
        pattern=r"^[a-z][a-zA-Z0-9]*$",
        needs=Needs.AST_TS,
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "Bad_Method" in matches[0].matched_value

def test_multiple_violations():
    """Should flag multiple naming violations in one file."""
    ctx = _make_ctx(
        "def BadOne():\n    pass\n"
        "def Also_Bad():\n    pass\n"
        "def good_one():\n    pass\n"
    )
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 2

def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="def Bad(): pass")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_]+$",
    )
    assert matcher.find(ctx) == []

def test_variable_naming():
    """Should check variable declarations in Python."""
    ctx = _make_ctx("BadVariable = 42\n")
    matcher = NamingConventionMatcher(
        declaration_types=["assignment"],  # ponytail: tree-sitter may not have this — using identifier
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    # ponytail: tree-sitter Python doesn't have a dedicated 'assignment' node
    # this test documents that — assignment is an expression_statement
    # for variable naming, use RegexMatcher on the raw text instead
    result = matcher.find(ctx)
    # Should return empty — no matching declaration_type nodes found
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_naming_convention.py -v`
Expected: FAIL — `NamingConventionMatcher` does not exist.

- [ ] **Step 3: Implement `NamingConventionMatcher`**

```python
# enforcer/matchers/naming_convention.py
"""NamingConventionMatcher: walks AST for declarations, checks names against a regex."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs

# ponytail: node types where the name is the first identifier child
_DECL_NODE_TYPES = {
    "function_definition": "function",     # Python def
    "function_declaration": "function",     # TS function
    "method_definition": "method",          # Python/TS method
    "method_declaration": "method",         # TS method declaration
    "class_definition": "class",            # Python class
    "class_declaration": "class",           # TS class
    "variable_declaration": "variable",     # TS const/let/var
}

@dataclass
class NamingConventionMatcher:
    """Walks AST for declaration nodes, flags names that don't match the required pattern.
    declaration_types: which node types to check (e.g. ['function_definition', 'class_definition']).
    pattern: regex the declaration name must match. If it doesn't match, the name is flagged."""
    declaration_types: list[str]
    pattern: str
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk(root):
            if node.type in self.declaration_types:
                name = self._extract_name(node)
                if name and not self._compiled.search(name):
                    matches.append(Match(
                        file=file_ctx.path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1] + 1,
                        matched_value=name,
                    ))
        return matches

    def _extract_name(self, node) -> str:
        # ponytail: name is the first identifier child for most declaration nodes
        for child in node.children:
            if child.type == "identifier":
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
            # Python uses 'identifier' too, but also check 'type_identifier'
            if child.type == "type_identifier":
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    def _walk(self, node):
        # ponytail: iterative DFS — avoids RecursionError on deeply nested AST
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))
```

- [ ] **Step 4: Export from `__init__.py`**

In `enforcer/matchers/__init__.py`, add:

```python
from enforcer.matchers.naming_convention import NamingConventionMatcher
```

Add `"NamingConventionMatcher"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_naming_convention.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/matchers/naming_convention.py enforcer/matchers/__init__.py tests/test_matchers/test_naming_convention.py
git commit -m "feat: NamingConventionMatcher — enforce naming conventions

Walks AST for declaration nodes (function/class/method/variable).
Extracts the declaration name (first identifier child).
Flags if name doesn't match required regex pattern.
Supports Python and TypeScript. Iterative DFS — no RecursionError."
```

---

## Task 5: Enhanced AST predicates — `HasDecoratorPredicate`, `NodeNamePredicate`

**Files:**
- Create: `enforcer/predicates/ast.py`
- Modify: `enforcer/predicates/__init__.py`
- Test: `tests/test_predicates/test_ast_predicates.py`

**Context:** Predicates filter matches after matchers produce them. `HasDecoratorPredicate` checks if a function/class match has a decorator (e.g., only enforce naming on `@pytest.fixture` functions). `NodeNamePredicate` checks the matched node's name against a regex.

- [ ] **Step 1: Write failing test**

```python
# tests/test_predicates/test_ast_predicates.py
"""Tests for AST predicates: HasDecoratorPredicate, NodeNamePredicate."""
import re
from enforcer.predicates.ast import HasDecoratorPredicate, NodeNamePredicate
from enforcer.types import Match, FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def test_has_decorator_predicate_pass():
    """HasDecoratorPredicate should pass when the match's node has a decorator."""
    source = (
        "@pytest.fixture\n"
        "def my_fixture():\n"
        "    return 42\n"
    )
    ctx = _make_ctx(source)
    # Find the function node and create a match at its location
    root = ctx.ast.root_node
    func_node = None
    for child in root.children:
        if child.type == "function_definition":
            func_node = child
            break
    assert func_node is not None
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="my_fixture",
    )
    match._file_ctx = ctx  # ponytail: attach context for predicate to access AST
    pred = HasDecoratorPredicate()
    assert pred.test(match) is True

def test_has_decorator_predicate_fail():
    """HasDecoratorPredicate should fail when no decorator."""
    source = "def no_decorator():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = next(c for c in root.children if c.type == "function_definition")
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="no_decorator",
    )
    match._file_ctx = ctx
    pred = HasDecoratorPredicate()
    assert pred.test(match) is False

def test_has_decorator_with_pattern():
    """HasDecoratorPredicate should filter by decorator name pattern."""
    source = (
        "@app.route('/api')\n"
        "def endpoint():\n"
        "    pass\n"
    )
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = next(c for c in root.children if c.type == "function_definition")
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="endpoint",
    )
    match._file_ctx = ctx
    pred = HasDecoratorPredicate(pattern=r"app\.route")
    assert pred.test(match) is True

    pred_no = HasDecoratorPredicate(pattern=r"pytest\.fixture")
    assert pred_no.test(match) is False

def test_node_name_predicate_match():
    """NodeNamePredicate should pass when node name matches pattern."""
    source = "def test_foo():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = next(c for c in root.children if c.type == "function_definition")
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="test_foo",
    )
    match._file_ctx = ctx
    pred = NodeNamePredicate(pattern=r"^test_")
    assert pred.test(match) is True

def test_node_name_predicate_no_match():
    """NodeNamePredicate should fail when node name doesn't match."""
    source = "def not_a_test():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = next(c for c in root.children if c.type == "function_definition")
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="not_a_test",
    )
    match._file_ctx = ctx
    pred = NodeNamePredicate(pattern=r"^test_")
    assert pred.test(match) is False

def test_predicate_without_ctx_returns_false():
    """Predicates should return False when no _file_ctx attached (defensive)."""
    match = Match(file="test.py", line=1, matched_value="foo")
    assert HasDecoratorPredicate().test(match) is False
    assert NodeNamePredicate(pattern=r"foo").test(match) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_predicates/test_ast_predicates.py -v`
Expected: FAIL — module `enforcer.predicates.ast` does not exist.

- [ ] **Step 3: Implement predicates**

```python
# enforcer/predicates/ast.py
"""AST-aware predicates: HasDecoratorPredicate, NodeNamePredicate."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match

def _get_node_at_line(file_ctx, line: int):
    """Find the AST node at the given line. Returns None if no AST or line not found."""
    if not file_ctx or not file_ctx.ast:
        return None
    root = file_ctx.ast.root_node
    # ponytail: walk to find node starting at this line
    stack = [root]
    while stack:
        node = stack.pop()
        if node.start_point[0] + 1 == line:
            return node
        stack.extend(reversed(node.children))
    return None

@dataclass
class HasDecoratorPredicate:
    """Passes if the matched node (or its parent) has a decorator.
    If pattern is set, the decorator text must match it."""
    pattern: str | None = None

    def __post_init__(self):
        if self.pattern:
            self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        ctx = getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        # ponytail: decorators are siblings BEFORE the decorated node in tree-sitter
        # check previous children of parent
        parent = node.parent
        if not parent:
            return False
        idx = parent.children.index(node)
        for i in range(idx - 1, -1, -1):
            sibling = parent.children[i]
            if sibling.type == "decorator":
                raw = sibling.text
                text = raw.decode() if hasattr(raw, "decode") else str(raw)
                if not self.pattern or self._compiled.search(text):
                    return True
            elif sibling.type not in ("decorator", "comment", "newline"):
                break
        return False

@dataclass
class NodeNamePredicate:
    """Passes if the matched node's name matches the regex pattern."""
    pattern: str

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        ctx = getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        # extract name: first identifier child
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                raw = child.text
                name = raw.decode() if hasattr(raw, "decode") else str(raw)
                return bool(self._compiled.search(name))
        return False
```

- [ ] **Step 4: Export from `__init__.py`**

In `enforcer/predicates/__init__.py`, add:

```python
from enforcer.predicates.ast import HasDecoratorPredicate, NodeNamePredicate
```

Add `"HasDecoratorPredicate", "NodeNamePredicate"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_predicates/test_ast_predicates.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/predicates/ast.py enforcer/predicates/__init__.py tests/test_predicates/test_ast_predicates.py
git commit -m "feat: AST predicates — HasDecoratorPredicate, NodeNamePredicate

HasDecoratorPredicate: filter matches to only those with decorators
(optionally matching a decorator name pattern). NodeNamePredicate:
filter by the matched node's declared name. Predicates access the AST
via match._file_ctx (attached by the runner)."
```

---

## Task 6: Wire `_file_ctx` attachment in `RuleRunner` (enabler for AST predicates)

**Files:**
- Modify: `enforcer/rule.py:50-74` — attach `match._file_ctx = file_ctx` before predicates
- Test: `tests/test_predicates/test_ast_predicates.py` (verify integration)

**Context:** AST predicates need access to the `FileContext` to look up nodes. The `Rule.check()` method stamps `rule_id`, `severity`, etc. on matches — it should also attach `_file_ctx` so predicates can use it.

- [ ] **Step 1: Write integration test**

```python
# tests/test_predicates/test_ast_predicates.py (append to existing file)

def test_predicate_works_through_rule_check():
    """HasDecoratorPredicate should work when invoked through Rule.check()."""
    from enforcer.rule import Rule
    from enforcer.types import Severity
    from enforcer.matchers.naming_convention import NamingConventionMatcher

    source = (
        "@app.route('/api')\n"
        "def Bad_Name():\n"
        "    pass\n"
        "def good_name():\n"
        "    pass\n"
    )
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)

    rule = Rule(
        id="naming",
        severity=Severity.WARN,
        matchers=[NamingConventionMatcher(
            declaration_types=["function_definition"],
            pattern=r"^[a-z_][a-z0-9_]*$",
        )],
        file_globs=["*.py"],
        predicates=[HasDecoratorPredicate(pattern=r"app\.route")],
        message="Decorated function {matched_value} must be snake_case",
    )
    matches = rule.check(ctx, {})
    # Only Bad_Name has @app.route decorator — should be the only match
    assert len(matches) == 1
    assert "Bad_Name" in matches[0].matched_value
    assert "good_name" not in [m.matched_value for m in matches]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_predicates/test_ast_predicates.py::test_predicate_works_through_rule_check -v`
Expected: FAIL — `_file_ctx` not attached, predicate returns False for all matches.

- [ ] **Step 3: Attach `_file_ctx` in `Rule.check()`**

In `enforcer/rule.py`, modify the `check()` method. After the diff_only filter and before predicates:

```python
        # ponytail: attach file_ctx to each match so AST predicates can access the AST
        for m in all_matches:
            m._file_ctx = file_ctx

        for pred in self.predicates:
            all_matches = [m for m in all_matches if pred.test(m)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_predicates/test_ast_predicates.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add enforcer/rule.py tests/test_predicates/test_ast_predicates.py
git commit -m "feat: attach _file_ctx to matches — enables AST predicates

Rule.check() now sets match._file_ctx = file_ctx before running
predicates. AST predicates (HasDecoratorPredicate, NodeNamePredicate)
use this to look up the matched node in the tree."
```

---

## Task 7: Auto-fix infrastructure — `FixProvider` protocol and `apply_fixes()`

**Files:**
- Create: `enforcer/fix.py`
- Modify: `enforcer/types.py` — add `fix_applied: str` to `Match`
- Test: `tests/test_fix.py`

**Context:** Matchers can optionally provide a `fix()` method that returns patched source. The fix orchestrator groups matches by file, applies fixes in reverse line order (to preserve line numbers), and writes the result.

- [ ] **Step 1: Write failing test**

```python
# tests/test_fix.py
"""Tests for auto-fix infrastructure."""
import tempfile
from pathlib import Path
from enforcer.fix import apply_fixes, FixResult
from enforcer.types import Match, Severity, FileContext

def test_apply_fixes_simple_replacement():
    """apply_fixes should replace matched text in the file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('hello')\nprint('world')\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-print",
                  severity=Severity.ERROR, matched_value="print('hello')"),
            Match(file="test.py", line=2, column=0, rule_id="no-print",
                  severity=Severity.ERROR, matched_value="print('world')"),
        ]
        # Fix: replace print( with logger.debug(
        def fix_fn(file_ctx: FileContext, match: Match) -> str:
            raw = file_ctx.raw or ""
            lines = raw.splitlines()
            if match.line <= len(lines):
                fixed = lines[match.line - 1].replace("print(", "logger.debug(")
                lines[match.line - 1] = fixed
            return "\n".join(lines) + "\n"

        results = apply_fixes(matches, tmpdir, {"no-print": fix_fn})
        assert len(results) == 1  # one result per file
        assert "logger.debug" in fpath.read_text()
        assert "print(" not in fpath.read_text()

def test_apply_fixes_no_fix_provider():
    """apply_fixes should skip matches with no fix provider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('hello')\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-fix-rule",
                  severity=Severity.ERROR, matched_value="print('hello')"),
        ]
        results = apply_fixes(matches, tmpdir, {})
        assert len(results) == 0
        # File unchanged
        assert "print('hello')" in fpath.read_text()

def test_apply_fixes_multiple_rules():
    """apply_fixes should apply fixes from different rules to the same file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("import os\nTODO: fix this\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-os-import",
                  severity=Severity.ERROR, matched_value="import os"),
            Match(file="test.py", line=2, column=0, rule_id="no-todo",
                  severity=Severity.WARN, matched_value="TODO: fix this"),
        ]
        def fix_import(ctx, m):
            return (ctx.raw or "").replace("import os\n", "")

        def fix_todo(ctx, m):
            return (ctx.raw or "").replace("TODO: ", "FIXME: ")

        results = apply_fixes(matches, tmpdir, {
            "no-os-import": fix_import,
            "no-todo": fix_todo,
        })
        content = fpath.read_text()
        assert "import os" not in content
        assert "FIXME: fix this" in content

def test_apply_fixes_file_not_found():
    """apply_fixes should skip files that don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        matches = [
            Match(file="nonexistent.py", line=1, rule_id="x", matched_value="x"),
        ]
        results = apply_fixes(matches, tmpdir, {"x": lambda ctx, m: ""})
        assert len(results) == 0

def test_fix_result_has_summary():
    """FixResult should contain file path, matches fixed, and new content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('x')\n")

        matches = [
            Match(file="test.py", line=1, rule_id="no-print", matched_value="print('x')"),
        ]
        def fix_fn(ctx, m):
            return (ctx.raw or "").replace("print(", "logger.debug(")

        results = apply_fixes(matches, tmpdir, {"no-print": fix_fn})
        assert len(results) == 1
        r = results[0]
        assert r.path == "test.py"
        assert r.fixes_applied == 1
        assert "logger.debug" in r.new_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fix.py -v`
Expected: FAIL — `enforcer.fix` module does not exist.

- [ ] **Step 3: Add `fix_applied` field to `Match`**

In `enforcer/types.py`, add field to `Match`:

```python
@dataclass
class Match:
    file: str
    line: int
    column: int = 0
    message: str = ""
    rule_id: str = ""
    severity: Severity = Severity.WARN
    fix_instruction: str = ""
    llm_response: str = ""
    matched_value: str = ""
    fix_applied: str = ""
```

- [ ] **Step 4: Implement `apply_fixes()`**

```python
# enforcer/fix.py
"""Auto-fix infrastructure: apply_fixes groups matches by file and applies fix functions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext

@dataclass
class FixResult:
    """Result of applying fixes to one file."""
    path: str
    fixes_applied: int
    new_content: str

def apply_fixes(matches: list[Match], workspace: str,
                fix_providers: dict[str, callable]) -> list[FixResult]:
    """Group matches by file, apply fix functions, write results.
    fix_providers maps rule_id to a fix function (FileContext, Match) -> str (new content).
    Returns one FixResult per file that had fixes applied."""
    by_file: dict[str, list[Match]] = {}
    for m in matches:
        fn = fix_providers.get(m.rule_id)
        if not fn:
            continue
        by_file.setdefault(m.file, []).append(m)

    results: list[FixResult] = []
    for file_path, file_matches in by_file.items():
        full_path = Path(workspace, file_path)
        if not full_path.exists():
            continue
        raw = full_path.read_text(encoding="utf-8", errors="replace")
        ctx = FileContext(path=file_path, raw=raw)
        content = raw
        applied = 0
        for m in file_matches:
            fn = fix_providers.get(m.rule_id)
            if not fn:
                continue
            new_content = fn(ctx, m)
            if new_content != content:
                content = new_content
                ctx.raw = content
                m.fix_applied = "applied"
                applied += 1
        if applied > 0:
            full_path.write_text(content, encoding="utf-8")
            results.append(FixResult(path=file_path, fixes_applied=applied, new_content=content))
    return results
```

- [ ] **Step 5: Export from `enforcer/__init__.py`**

Add `from enforcer.fix import apply_fixes, FixResult` to `enforcer/__init__.py` and to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_fix.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass. `fix_applied` field defaults to `""` — backward compatible.

- [ ] **Step 8: Commit**

```bash
git add enforcer/fix.py enforcer/types.py enforcer/__init__.py tests/test_fix.py
git commit -m "feat: auto-fix infrastructure — apply_fixes, FixResult

apply_fixes() groups matches by file, calls fix provider functions
(registered per rule_id), writes patched content. Matchers can
provide fix functions that return new file content. Match gets
fix_applied field to track which were fixed."
```

---

## Task 8: CLI `--fix` flag and metadata rule execution

**Files:**
- Modify: `enforcer/cli.py:48-128`
- Test: `tests/test_cli_fix.py`

**Context:** Add `--fix` flag to `check` command. When set, after running rules, call `apply_fixes()` with fix providers collected from matchers. Also execute metadata rules (branch/commit) and include their results.

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_fix.py
"""Tests for CLI --fix flag."""
import tempfile
from pathlib import Path
from click.testing import CliRunner
from enforcer.cli import cli

def test_fix_flag_applies_fixes():
    """--fix should apply fix functions and modify files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('hello')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm", "--fix"])
        content = Path(tmpdir, "test.py").read_text()
        assert "logger.debug" in content
        assert "print(" not in content

def test_fix_flag_reports_applied():
    """--fix should report which fixes were applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('x')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm", "--fix"])
        assert "1 fix" in result.output or "fixed" in result.output.lower()

def test_no_fix_flag_does_not_modify():
    """Without --fix, files should not be modified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('hello')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        content = Path(tmpdir, "test.py").read_text()
        assert "print('hello')" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_fix.py -v`
Expected: FAIL — `--fix` flag doesn't exist.

- [ ] **Step 3: Add `--fix` flag and `fix` field to `Rule`**

In `enforcer/rule.py`, add `fix` field:

```python
@dataclass
class Rule:
    # ... existing fields ...
    rule_type: RuleType = RuleType.CONTENT
    fix: Callable | None = None
```

- [ ] **Step 4: Update CLI `check` command**

In `enforcer/cli.py`, add `--fix` flag:

```python
@click.option("--fix", is_flag=True, help="Apply auto-fixes where available")
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings, fix):
```

After `all_matches = runner.run_rules_for_file(...)`, add metadata rule execution:

```python
    # Run metadata rules (branch name, commit message)
    meta_matches = runner.run_metadata_rules(shared_ctx)
    all_matches.extend(meta_matches)
```

After all matches are collected and before reporter, add fix logic:

```python
    if fix:
        from enforcer.fix import apply_fixes
        fix_providers = {r.id: r.fix for r in config.rules if r.fix is not None}
        results = apply_fixes(all_matches, ws, fix_providers)
        total_fixes = sum(r.fixes_applied for r in results)
        if total_fixes > 0:
            click.echo(f"Applied {total_fixes} fix(es) across {len(results)} file(s).", err=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_fix.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add enforcer/cli.py enforcer/rule.py tests/test_cli_fix.py
git commit -m "feat: --fix flag — apply auto-fixes during check

CLI check command now accepts --fix. Collects fix functions from
rules (Rule.fix field), calls apply_fixes() to patch files in-place.
Also runs metadata rules (branch/commit) and includes results in
the check output."
```

---

## Task 9: Add naming/branch/commit rules to ASML example config

**Files:**
- Modify: `examples/asml_enforcer_config.py`
- Test: `tests/test_asml_config_updates.py` (extend)

- [ ] **Step 1: Write test**

```python
# Append to tests/test_asml_config_updates.py

def test_asml_config_has_branch_rule():
    config = load_config("examples/asml_enforcer_config.py")
    rule_ids = [r.id for r in config.rules]
    assert "branch-naming" in rule_ids

def test_asml_config_has_commit_message_rule():
    config = load_config("examples/asml_enforcer_config.py")
    rule_ids = [r.id for r in config.rules]
    assert "commit-message-format" in rule_ids

def test_asml_config_has_naming_rule():
    config = load_config("examples/asml_enforcer_config.py")
    rule_ids = [r.id for r in config.rules]
    assert "backend-function-naming" in rule_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_asml_config_updates.py -v`
Expected: FAIL — rules don't exist.

- [ ] **Step 3: Add rules to ASML config**

In `examples/asml_enforcer_config.py`, update imports:

```python
from enforcer.types import RuleType
from enforcer.matchers import (
    RegexMatcher,
    LineCountMatcher,
    PathNotMatchingMatcher,
    AlwaysMatcher,
    ImportMatcher,
    FunctionComplexityMatcher,
    PairedFileMatcher,
    BranchNameMatcher,
    CommitMessageMatcher,
    NamingConventionMatcher,
)
```

Add rules at the end of `RULES`:

```python
    # ─── Git metadata: branch naming ─────────────────────────────────────
    Rule(
        id="branch-naming",
        severity=Severity.ERROR,
        matchers=[BranchNameMatcher(pattern=r"^(feature|fix|hotfix|chore|docs|refactor)/")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Branch '{matched_value}' doesn't match required pattern: type/description",
        fix_instruction="Rename: git branch -m <type>/<description>",
    ),

    # ─── Git metadata: commit message format ─────────────────────────────
    Rule(
        id="commit-message-format",
        severity=Severity.WARN,
        matchers=[CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Commit message '{matched_value}' doesn't follow Conventional Commits",
        fix_instruction="Use: type(scope): description (e.g. feat(api): add endpoint)",
    ),

    # ─── Backend: function naming ────────────────────────────────────────
    Rule(
        id="backend-function-naming",
        severity=Severity.WARN,
        matchers=[NamingConventionMatcher(
            declaration_types=["function_definition"],
            pattern=r"^[a-z_][a-z0-9_]*$",
        )],
        file_globs=["backend/app/**/*.py"],
        exclude_globs=["backend/alembic/**"],
        message="Function '{matched_value}' at {file}:{line} must be snake_case",
        fix_instruction="Rename to snake_case.",
        diff_only=True,
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_asml_config_updates.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add examples/asml_enforcer_config.py tests/test_asml_config_updates.py
git commit -m "feat: ASML config — branch naming, commit message, function naming rules

Adds 3 new rules: branch-naming (feature/fix/hotfix prefix),
commit-message-format (Conventional Commits), backend-function-naming
(snake_case). First two are METADATA rules (run once per check).
Function naming uses NamingConventionMatcher with diff_only=True."
```

---

## Task 10: Update README with Tier 2 features

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update matchers table**

Add to the matchers table in README.md:

```markdown
| `BranchNameMatcher(pattern=)` | Checks current git branch against regex. METADATA rule. |
| `CommitMessageMatcher(pattern=)` | Checks commit message first line against regex. METADATA rule. |
| `NamingConventionMatcher(declaration_types=, pattern=)` | Walks AST for declarations, flags names not matching regex. |
```

- [ ] **Step 2: Update predicates table**

Add to predicates table:

```markdown
| `HasDecoratorPredicate(pattern=)` | Passes if matched node has a decorator (optionally matching pattern). |
| `NodeNamePredicate(pattern=)` | Passes if matched node's name matches regex. |
```

- [ ] **Step 3: Add auto-fix section**

After the "Diff-awareness" section, add:

```markdown
## Auto-fix

Rules can provide a `fix` function that patches the file content. Enable with `--fix`:

```bash
enforcer check --staged --fix
```

```python
Rule(
    id="no-print",
    severity=Severity.ERROR,
    matchers=[RegexMatcher(r"print\s*\(")],
    file_globs=["**/*.py"],
    message="print() at {file}:{line}",
    fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug("),
)
```

The fix function receives `(FileContext, Match) -> str` (new file content). Fixes are applied per-file, in match order. Files are written in-place.

## Metadata rules (branch/commit)

Rules with `rule_type=RuleType.METADATA` run once per check, not per-file. Used for branch name and commit message enforcement:

```python
Rule(
    id="branch-naming",
    severity=Severity.ERROR,
    matchers=[BranchNameMatcher(pattern=r"^(feature|fix|hotfix)/")],
    file_globs=["*"],
    rule_type=RuleType.METADATA,
    message="Branch '{matched_value}' doesn't match required pattern",
)
```
```

- [ ] **Step 4: Add `Rule` fields table entries**

Add to the Rule fields table:

```markdown
| `rule_type` | `RuleType` | `CONTENT` (per-file) or `METADATA` (once per check). Default `CONTENT`. |
| `fix` | `Callable \| None` | Function `(FileContext, Match) -> str` returning patched content. Default `None`. |
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document Tier 2 features — auto-fix, metadata rules, new matchers"
```

---

## Self-Review

### Spec coverage
- ✅ Auto-fix (`--fix`) — Task 7 (infrastructure) + Task 8 (CLI)
- ✅ NamingConventionMatcher — Task 4
- ✅ Branch/commit-message rules — Tasks 2, 3
- ✅ Enhanced AST predicates — Task 5
- ✅ Rule priority/ordering — deferred (YAGNI, existing rule order is sufficient)
- ✅ Duplicate code detection — deferred (YAGNI, high complexity, no demand)

### Placeholder scan
- No TBD, TODO, "implement later"
- All code blocks contain actual implementation
- All test blocks contain actual test code

### Type consistency
- `RuleType` used consistently in types.py, rule.py, runner.py
- `FixResult` defined in fix.py, used in cli.py
- `fix` field on Rule is `Callable | None`, used in cli.py via `r.fix`
- `_file_ctx` attached in rule.py:check(), consumed in predicates/ast.py
- `apply_fixes(matches, workspace, fix_providers)` signature consistent between fix.py and cli.py
