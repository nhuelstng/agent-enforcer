# Pre-Commit Agent Enforcer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool (`enforcer`) that deterministically detects convention deviations and blocks commits, with a composable DSL for rules (regex + AST matchers, logical combinators, predicates, LLM consequences), parse-once optimization, JSON/text output, CLI + MCP server.

**Architecture:** Standalone Python package with composable matchers/predicates/combinators. Config-as-code (`enforcer_config.py`). Pre-commit hook shells out to CLI. MCP server for agent self-check. tree-sitter for unified AST. LLM calls fire only on deterministic rule failure, in parallel.

**Tech Stack:** Python 3.11+, tree-sitter, httpx, click, pytest, pytest-mock, pytest-cov

**Spec:** `docs/superpowers/specs/2026-06-26-pre-commit-agent-enforcer-design.md`

---

## File Structure

```
enforcer/
├── pyproject.toml
├── enforcer/
│   ├── __init__.py            # public API exports
│   ├── types.py               # Severity, Needs, Match, FileContext, LLMConsequence
│   ├── rule.py                # Rule dataclass + check logic
│   ├── matchers/
│   │   ├── __init__.py        # exports all matchers
│   │   ├── regex.py           # RegexMatcher
│   │   ├── ast_node.py        # AstNodeMatcher
│   │   ├── line_count.py      # LineCountMatcher
│   │   ├── char_count.py      # CharCountMatcher
│   │   ├── path_pattern.py    # PathNotMatchingMatcher
│   │   ├── comment_density.py # CommentPerFunctionMatcher
│   │   └── allowlist.py       # AllowlistMatcher
│   ├── combinators/
│   │   ├── __init__.py        # exports AllOf, AnyOf, OneOf, Not, NoneOf
│   │   └── core.py            # all combinator implementations
│   ├── predicates/
│   │   ├── __init__.py        # exports all predicates
│   │   ├── int_compare.py     # IntPredicate
│   │   ├── string_length.py   # StringLengthPredicate
│   │   ├── string_matches.py  # StringMatchesPredicate, StringNotMatchesPredicate
│   │   └── combinators.py    # All, Any, NotP
│   ├── config.py              # config loader
│   ├── context.py             # FileContext builder (parse-once)
│   ├── runner.py              # Rule Runner
│   ├── reporter.py            # JSON/text output
│   ├── llm.py                 # LLM Executor
│   ├── cli.py                 # CLI entry point
│   ├── mcp_server.py          # MCP server
│   └── parsers/
│       ├── __init__.py
│       ├── tree_sitter.py     # tree-sitter wrapper
│       └── language.py        # file extension → language
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_matchers/
│   ├── test_combinators/
│   ├── test_predicates/
│   ├── test_rule.py
│   ├── test_config.py
│   ├── test_context.py
│   ├── test_runner.py
│   ├── test_reporter.py
│   ├── test_llm.py
│   ├── test_cli.py
│   ├── test_parse_once.py
│   ├── test_exclude_globs.py
│   └── test_integration.py
└── enforcer_config.py         # example config
```

---

## Task 1: Project scaffold + core types

**Files:**
- Create: `pyproject.toml`
- Create: `enforcer/__init__.py`
- Create: `enforcer/types.py`
- Create: `tests/conftest.py`
- Create: `tests/test_types.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "pre-commit-agent-enforcer"
version = "0.1.0"
description = "Deterministic convention enforcement for coding agents"
requires-python = ">=3.11"
dependencies = [
    "tree-sitter>=0.21",
    "tree-sitter-typescript>=0.21",
    "tree-sitter-python>=0.21",
    "tree-sitter-css>=0.21",
    "httpx>=0.27",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "pytest-cov>=4.1",
]
mcp = ["mcp>=0.1"]

[project.scripts]
enforcer = "enforcer.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create enforcer/types.py**

```python
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable

class Severity(Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"

class Needs(Enum):
    RAW = "raw"
    AST_TS = "ast_ts"
    AST_PY = "ast_py"
    AST_CSS = "ast_css"

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

@dataclass
class FileContext:
    path: str
    raw: str | None = None
    ast: object | None = None

@dataclass
class LLMConsequence:
    provider: str
    model: str
    prompt: str
    timeout: int = 30
```

- [ ] **Step 3: Create enforcer/__init__.py**

```python
from enforcer.types import Severity, Needs, Match, FileContext, LLMConsequence

__all__ = ["Severity", "Needs", "Match", "FileContext", "LLMConsequence"]
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import pytest
from enforcer import FileContext

@pytest.fixture
def sample_ts_file():
    return FileContext(
        path="src/app/x.ts",
        raw="const x = #fff;\nconst y = 1;\nconsole.log('hello');\n",
    )

@pytest.fixture
def sample_scss_file():
    return FileContext(
        path="src/styles/colors.scss",
        raw="--color-primary: #fff;\n--color-secondary: #000;\n",
    )

@pytest.fixture
def sample_readme():
    return FileContext(
        path="README.md",
        raw="\n".join(f"line {i}" for i in range(1, 201)),
    )
```

- [ ] **Step 5: Write test for types**

Create `tests/test_types.py`:

```python
from enforcer import Severity, Needs, Match, FileContext, LLMConsequence

def test_severity_values():
    assert Severity.ERROR.value == "error"
    assert Severity.WARN.value == "warn"
    assert Severity.INFO.value == "info"

def test_needs_values():
    assert Needs.RAW.value == "raw"
    assert Needs.AST_TS.value == "ast_ts"

def test_match_defaults():
    m = Match(file="x.ts", line=1)
    assert m.column == 0
    assert m.message == ""
    assert m.severity == Severity.WARN
    assert m.matched_value == ""

def test_file_context():
    ctx = FileContext(path="x.ts")
    assert ctx.raw is None
    assert ctx.ast is None

def test_llm_consequence():
    c = LLMConsequence(provider="p", model="m", prompt="x")
    assert c.timeout == 30
```

- [ ] **Step 6: Install + run tests**

```bash
pip install -e ".[dev]"
pytest tests/test_types.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml enforcer/__init__.py enforcer/types.py tests/conftest.py tests/test_types.py
git commit -m "feat: project scaffold + core types"
```

---

## Task 2: RegexMatcher

**Files:**
- Create: `enforcer/matchers/__init__.py`
- Create: `enforcer/matchers/regex.py`
- Create: `tests/test_matchers/__init__.py`
- Create: `tests/test_matchers/test_regex_matcher.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_matchers/test_regex_matcher.py`:

```python
import pytest
from enforcer import FileContext, Needs
from enforcer.matchers import RegexMatcher

def test_regex_finds_all_matches():
    ctx = FileContext(path="x.ts", raw="color: #fff; bg: #aabbcc; border: #123456;")
    matcher = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")
    matches = matcher.find(ctx)
    assert len(matches) == 3
    assert matches[0].matched_value == "#fff"
    assert matches[0].line == 1
    assert matches[0].column == 7
    assert matches[1].matched_value == "#aabbcc"
    assert matches[2].matched_value == "#123456"

def test_regex_multiline():
    ctx = FileContext(path="x.ts", raw="color: #fff;\nbg: #aabbcc;\n")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert len(matches) == 2
    assert matches[0].line == 1
    assert matches[1].line == 2

def test_regex_no_matches():
    ctx = FileContext(path="x.ts", raw="color: var(--color-primary);")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert matches == []

def test_regex_empty_file():
    ctx = FileContext(path="x.ts", raw="")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert matches == []

def test_regex_needs_raw():
    assert RegexMatcher(r"test").needs == Needs.RAW

def test_regex_column_position():
    ctx = FileContext(path="x.ts", raw="  #fff")
    matches = RegexMatcher(r"#fff").find(ctx)
    assert matches[0].column == 3

def test_regex_matches_file_field():
    ctx = FileContext(path="x.ts", raw="#fff")
    matches = RegexMatcher(r"#fff").find(ctx)
    assert matches[0].file == "x.ts"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_matchers/test_regex_matcher.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Write implementation**

Create `enforcer/matchers/regex.py`:

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match, FileContext, Needs

@dataclass
class RegexMatcher:
    pattern: str | Pattern
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        matches: list[Match] = []
        if not file_ctx.raw:
            return matches
        for i, line in enumerate(file_ctx.raw.splitlines(), 1):
            for m in re.finditer(self.pattern, line):
                matches.append(Match(
                    file=file_ctx.path,
                    line=i,
                    column=m.start() + 1,
                    matched_value=m.group(),
                ))
        return matches
```

Create `enforcer/matchers/__init__.py`:

```python
from enforcer.matchers.regex import RegexMatcher

__all__ = ["RegexMatcher"]
```

Create `tests/test_matchers/__init__.py` (empty file).

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matchers/test_regex_matcher.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/__init__.py enforcer/matchers/regex.py tests/test_matchers/__init__.py tests/test_matchers/test_regex_matcher.py
git commit -m "feat: RegexMatcher"
```

---

## Task 3: LineCountMatcher + CharCountMatcher + PathNotMatchingMatcher

**Files:**
- Create: `enforcer/matchers/line_count.py`
- Create: `enforcer/matchers/char_count.py`
- Create: `enforcer/matchers/path_pattern.py`
- Create: `tests/test_matchers/test_line_count_matcher.py`
- Create: `tests/test_matchers/test_char_count_matcher.py`
- Create: `tests/test_matchers/test_path_pattern_matcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_matchers/test_line_count_matcher.py`:

```python
from enforcer import FileContext, Needs
from enforcer.matchers import LineCountMatcher

def test_line_count_exceeds():
    ctx = FileContext(path="README.md", raw="\n".join(["line"] * 201))
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "201"

def test_line_count_at_limit():
    ctx = FileContext(path="README.md", raw="\n".join(["line"] * 200))
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_below_limit():
    ctx = FileContext(path="README.md", raw="one line")
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_empty_file():
    ctx = FileContext(path="README.md", raw="")
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_needs_raw():
    assert LineCountMatcher(max_lines=10).needs == Needs.RAW
```

Create `tests/test_matchers/test_char_count_matcher.py`:

```python
from enforcer import FileContext, Needs
from enforcer.matchers import CharCountMatcher

def test_char_count_exceeds():
    ctx = FileContext(path="x.ts", raw="x" * 101)
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "101"

def test_char_count_at_limit():
    ctx = FileContext(path="x.ts", raw="x" * 100)
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_below_limit():
    ctx = FileContext(path="x.ts", raw="short")
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_empty_file():
    ctx = FileContext(path="x.ts", raw="")
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_needs_raw():
    assert CharCountMatcher(max_chars=10).needs == Needs.RAW
```

Create `tests/test_matchers/test_path_pattern_matcher.py`:

```python
from enforcer import FileContext, Needs
from enforcer.matchers import PathNotMatchingMatcher

def test_path_not_matching():
    ctx = FileContext(path="src/app/x.ts")
    matches = PathNotMatchingMatcher("**/constants.ts").find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "src/app/x.ts"

def test_path_matches():
    ctx = FileContext(path="src/app/constants.ts")
    matches = PathNotMatchingMatcher("**/constants.ts").find(ctx)
    assert matches == []

def test_path_needs():
    assert PathNotMatchingMatcher("*.ts").needs != Needs.RAW
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_matchers/test_line_count_matcher.py tests/test_matchers/test_char_count_matcher.py tests/test_matchers/test_path_pattern_matcher.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementations**

Create `enforcer/matchers/line_count.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class LineCountMatcher:
    max_lines: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        count = len(file_ctx.raw.splitlines())
        if count > self.max_lines:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
```

Create `enforcer/matchers/char_count.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CharCountMatcher:
    max_chars: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        count = len(file_ctx.raw)
        if count > self.max_chars:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
```

Create `enforcer/matchers/path_pattern.py`:

```python
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class PathNotMatchingMatcher:
    pattern: str
    needs: Needs | None = None

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not fnmatch.fnmatch(file_ctx.path, self.pattern):
            return [Match(file=file_ctx.path, line=0, matched_value=file_ctx.path)]
        return []
```

Update `enforcer/matchers/__init__.py`:

```python
from enforcer.matchers.regex import RegexMatcher
from enforcer.matchers.line_count import LineCountMatcher
from enforcer.matchers.char_count import CharCountMatcher
from enforcer.matchers.path_pattern import PathNotMatchingMatcher

__all__ = [
    "RegexMatcher",
    "LineCountMatcher",
    "CharCountMatcher",
    "PathNotMatchingMatcher",
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matchers/test_line_count_matcher.py tests/test_matchers/test_char_count_matcher.py tests/test_matchers/test_path_pattern_matcher.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/line_count.py enforcer/matchers/char_count.py enforcer/matchers/path_pattern.py enforcer/matchers/__init__.py tests/test_matchers/test_line_count_matcher.py tests/test_matchers/test_char_count_matcher.py tests/test_matchers/test_path_pattern_matcher.py
git commit -m "feat: LineCount, CharCount, PathNotMatching matchers"
```

---

## Task 4: AllowlistMatcher

**Files:**
- Create: `enforcer/matchers/allowlist.py`
- Create: `tests/test_matchers/test_allowlist_matcher.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_matchers/test_allowlist_matcher.py`:

```python
import re
import pytest
from enforcer import FileContext
from enforcer.matchers import AllowlistMatcher

def test_allowlist_finds_undefined():
    target_raw = "--color-primary: #fff; --color-secondary: #000;"
    file_raw = "var(--color-primary); var(--color-undefined); var(--color-missing);"
    target_ctx = FileContext(path="colors.scss", raw=target_raw)
    file_ctx = FileContext(path="x.ts", raw=file_raw)
    shared = {"colors.scss": target_ctx}
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    matches = matcher.find(file_ctx, shared)
    assert len(matches) == 2
    values = {m.matched_value for m in matches}
    assert values == {"color-undefined", "color-missing"}

def test_allowlist_all_defined():
    import re
    target_raw = "--color-primary: #fff; --color-secondary: #000;"
    file_raw = "var(--color-primary); var(--color-secondary);"
    shared = {"colors.scss": FileContext(path="colors.scss", raw=target_raw)}
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    matches = matcher.find(FileContext(path="x.ts", raw=file_raw), shared)
    assert matches == []

def test_allowlist_missing_target():
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(),
        consumer=lambda raw: {"foo"},
        read_target="**/missing.scss",
    )
    matches = matcher.find(FileContext(path="x.ts", raw=""), {})
    assert matches == []

def test_allowlist_needs_raw():
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(),
        consumer=lambda raw: set(),
        read_target="**/colors.scss",
    )
    assert matcher.needs == Needs.RAW
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_matchers/test_allowlist_matcher.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/matchers/allowlist.py`:

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Callable
from enforcer.types import Match, FileContext, Needs

@dataclass
class AllowlistMatcher:
    extractor: Callable[[str], set[str]]
    consumer: Callable[[str], set[str]]
    read_target: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        basename = os.path.basename(self.read_target.replace("**/", "").replace("*", ""))
        # Also try raw basename
        target_ctx = shared_ctx.get(basename) or shared_ctx.get(os.path.basename(self.read_target))
        if not target_ctx:
            return []
        if not file_ctx.raw or not target_ctx.raw:
            return []
        allowed = self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        undefined = used - allowed
        return [
            Match(file=file_ctx.path, line=0, matched_value=item)
            for item in undefined
        ]
```

Update `enforcer/matchers/__init__.py`:

```python
from enforcer.matchers.regex import RegexMatcher
from enforcer.matchers.line_count import LineCountMatcher
from enforcer.matchers.char_count import CharCountMatcher
from enforcer.matchers.path_pattern import PathNotMatchingMatcher
from enforcer.matchers.allowlist import AllowlistMatcher

__all__ = [
    "RegexMatcher",
    "LineCountMatcher",
    "CharCountMatcher",
    "PathNotMatchingMatcher",
    "AllowlistMatcher",
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matchers/test_allowlist_matcher.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/allowlist.py enforcer/matchers/__init__.py tests/test_matchers/test_allowlist_matcher.py
git commit -m "feat: AllowlistMatcher for cross-file context"
```

---

## Task 5: Logical combinators (AllOf, AnyOf, OneOf, Not, NoneOf)

**Files:**
- Create: `enforcer/combinators/__init__.py`
- Create: `enforcer/combinators/core.py`
- Create: `tests/test_combinators/__init__.py`
- Create: `tests/test_combinators/test_all_of.py`
- Create: `tests/test_combinators/test_any_of.py`
- Create: `tests/test_combinators/test_one_of.py`
- Create: `tests/test_combinators/test_not.py`
- Create: `tests/test_combinators/test_none_of.py`
- Create: `tests/test_combinators/test_nested_combinators.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_combinators/__init__.py` (empty).

Create `tests/test_combinators/test_all_of.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AllOf

def test_all_of_all_match():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_all_of_one_missing():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert matches == []

def test_all_of_empty():
    ctx = FileContext(path="x.ts", raw="")
    m = AllOf([RegexMatcher(r"test")])
    assert m.find(ctx) == []

def test_all_of_single_matcher():
    ctx = FileContext(path="x.ts", raw="#fff")
    m = AllOf([RegexMatcher(r"#fff")])
    matches = m.find(ctx)
    assert len(matches) == 1
```

Create `tests/test_combinators/test_any_of.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AnyOf

def test_any_of_one_matches():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = AnyOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        RegexMatcher(r"\bconst\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "const"

def test_any_of_all_match():
    ctx = FileContext(path="x.ts", raw="const #fff;")
    m = AnyOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_any_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AnyOf([
        RegexMatcher(r"#fff"),
        RegexMatcher(r"\bconst\b"),
    ])
    assert m.find(ctx) == []
```

Create `tests/test_combinators/test_one_of.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import OneOf

def test_one_of_exactly_one():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = OneOf([
        RegexMatcher(r"#fff"),
        RegexMatcher(r"\bconst\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_one_of_two_matchers_match():
    ctx = FileContext(path="x.ts", raw="const #fff;")
    m = OneOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    assert m.find(ctx) == []

def test_one_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = OneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bconst\b")])
    assert m.find(ctx) == []
```

Create `tests/test_combinators/test_not.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import Not

def test_not_matcher_absent():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = Not(RegexMatcher(r"#fff"), message_on_absence="No hex found")
    matches = m.find(ctx)
    assert len(matches) == 1
    assert "No hex found" in matches[0].message

def test_not_matcher_present():
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    m = Not(RegexMatcher(r"#fff"))
    assert m.find(ctx) == []

def test_not_default_message():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = Not(RegexMatcher(r"#fff"))
    matches = m.find(ctx)
    assert len(matches) == 1
```

Create `tests/test_combinators/test_none_of.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import NoneOf

def test_none_of_all_absent():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_none_of_one_present():
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    assert m.find(ctx) == []
```

Create `tests/test_combinators/test_nested_combinators.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AllOf, AnyOf, OneOf, Not, NoneOf

def test_nested_anyof_inside_allof():
    ctx = FileContext(path="x.ts", raw="console.log('x'); #fff;")
    m = AllOf([
        AnyOf([RegexMatcher(r"\bconsole\.log\b"), RegexMatcher(r"\bdebugger\b")]),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_nested_not_inside_allof():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        Not(RegexMatcher(r"\bdebugger\b")),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_deeply_nested():
    ctx = FileContext(path="x.ts", raw="console.log(#fff);")
    m = AllOf([
        AnyOf([
            Not(RegexMatcher(r"\bdebugger\b")),
            RegexMatcher(r"\bconsole\.log\b"),
        ]),
        Not(NoneOf([RegexMatcher(r"#fff")])),
    ])
    matches = m.find(ctx)
    assert len(matches) >= 2
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_combinators/ -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/combinators/core.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext
from enforcer.matchers.allowlist import AllowlistMatcher

def _run(matcher, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
    if isinstance(matcher, AllowlistMatcher):
        return matcher.find(file_ctx, shared_ctx or {})
    return matcher.find(file_ctx)

@dataclass
class AllOf:
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if all(r for r in results):
            return [m for r in results for m in r]
        return []

@dataclass
class AnyOf:
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return [m for r in results if r for m in r]
        return []

@dataclass
class OneOf:
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        non_empty = [r for r in results if r]
        if len(non_empty) == 1:
            return non_empty[0]
        return []

@dataclass
class Not:
    matcher: object
    message_on_absence: str = "Expected pattern not found."

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        results = _run(self.matcher, file_ctx, shared_ctx)
        if results:
            return []
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(absent)",
            message=self.message_on_absence,
        )]

@dataclass
class NoneOf:
    matchers: list
    message_on_absence: str = "All forbidden patterns absent."

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return []
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(all absent)",
            message=self.message_on_absence,
        )]
```

Create `enforcer/combinators/__init__.py`:

```python
from enforcer.combinators.core import AllOf, AnyOf, OneOf, Not, NoneOf

__all__ = ["AllOf", "AnyOf", "OneOf", "Not", "NoneOf"]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_combinators/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/combinators/__init__.py enforcer/combinators/core.py tests/test_combinators/__init__.py tests/test_combinators/test_all_of.py tests/test_combinators/test_any_of.py tests/test_combinators/test_one_of.py tests/test_combinators/test_not.py tests/test_combinators/test_none_of.py tests/test_combinators/test_nested_combinators.py
git commit -m "feat: logical combinators (AllOf, AnyOf, OneOf, Not, NoneOf)"
```

---

## Task 6: Predicates (IntPredicate, StringLengthPredicate, StringMatchesPredicate, + predicate combinators)

**Files:**
- Create: `enforcer/predicates/__init__.py`
- Create: `enforcer/predicates/int_compare.py`
- Create: `enforcer/predicates/string_length.py`
- Create: `enforcer/predicates/string_matches.py`
- Create: `enforcer/predicates/combinators.py`
- Create: `tests/test_predicates/__init__.py`
- Create: `tests/test_predicates/test_int_predicate.py`
- Create: `tests/test_predicates/test_string_length_predicate.py`
- Create: `tests/test_predicates/test_string_matches_predicate.py`
- Create: `tests/test_predicates/test_predicate_combinators.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_predicates/__init__.py` (empty).

Create `tests/test_predicates/test_int_predicate.py`:

```python
from enforcer import Match
from enforcer.predicates import IntPredicate

def test_int_greater_than():
    m = Match(file="x", line=1, matched_value="42")
    assert IntPredicate(op=">", value=10).test(m) is True
    assert IntPredicate(op=">", value=50).test(m) is False

def test_int_all_operators():
    m = Match(file="x", line=1, matched_value="5")
    assert IntPredicate(op=">", value=4).test(m)
    assert IntPredicate(op="<", value=6).test(m)
    assert IntPredicate(op=">=", value=5).test(m)
    assert IntPredicate(op="<=", value=5).test(m)
    assert IntPredicate(op="==", value=5).test(m)
    assert IntPredicate(op="!=", value=6).test(m)

def test_int_non_numeric():
    m = Match(file="x", line=1, matched_value="not_a_number")
    assert IntPredicate(op=">", value=10).test(m) is False

def test_int_negative():
    m = Match(file="x", line=1, matched_value="-5")
    assert IntPredicate(op="<", value=0).test(m) is True
```

Create `tests/test_predicates/test_string_length_predicate.py`:

```python
from enforcer import Match
from enforcer.predicates import StringLengthPredicate

def test_string_length():
    m = Match(file="x", line=1, matched_value="hello")
    assert StringLengthPredicate(op=">", value=3).test(m)
    assert StringLengthPredicate(op=">", value=5).test(m) is False
    assert StringLengthPredicate(op="==", value=5).test(m)

def test_string_length_empty():
    m = Match(file="x", line=1, matched_value="")
    assert StringLengthPredicate(op="==", value=0).test(m)

def test_string_length_ge():
    m = Match(file="x", line=1, matched_value="ab")
    assert StringLengthPredicate(op=">=", value=2).test(m)
    assert StringLengthPredicate(op=">=", value=3).test(m) is False
```

Create `tests/test_predicates/test_string_matches_predicate.py`:

```python
from enforcer import Match
from enforcer.predicates import StringMatchesPredicate, StringNotMatchesPredicate

def test_string_matches():
    m = Match(file="x", line=1, matched_value="#aabbcc")
    assert StringMatchesPredicate(r"^#").test(m)
    assert StringMatchesPredicate(r"^#ff").test(m) is False

def test_string_not_matches():
    m = Match(file="x", line=1, matched_value="var(--color)")
    assert StringNotMatchesPredicate(r"^#").test(m)
    assert StringNotMatchesPredicate(r"^var").test(m) is False

def test_string_matches_partial():
    m = Match(file="x", line=1, matched_value="color: #fff;")
    assert StringMatchesPredicate(r"#fff").test(m)
```

Create `tests/test_predicates/test_predicate_combinators.py`:

```python
from enforcer import Match
from enforcer.predicates import IntPredicate, All, Any, NotP

def test_all_predicates():
    m = Match(file="x", line=1, matched_value="42")
    p = All([IntPredicate(op=">", value=10), IntPredicate(op="<", value=100)])
    assert p.test(m)

def test_all_predicates_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = All([IntPredicate(op=">", value=10), IntPredicate(op="<", value=40)])
    assert not p.test(m)

def test_any_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = Any([IntPredicate(op=">", value=50), IntPredicate(op="<", value=50)])
    assert p.test(m)

def test_any_predicate_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = Any([IntPredicate(op=">", value=50), IntPredicate(op=">", value=50)])
    assert not p.test(m)

def test_not_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = NotP(IntPredicate(op=">", value=50))
    assert p.test(m)

def test_not_predicate_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = NotP(IntPredicate(op="<", value=50))
    assert not p.test(m)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_predicates/ -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementations**

Create `enforcer/predicates/int_compare.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

@dataclass
class IntPredicate:
    op: str
    value: int

    def test(self, match: Match) -> bool:
        try:
            val = int(match.matched_value)
        except (ValueError, TypeError):
            return False
        return _OPS[self.op](val, self.value)
```

Create `enforcer/predicates/string_length.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}

@dataclass
class StringLengthPredicate:
    op: str
    value: int

    def test(self, match: Match) -> bool:
        return _OPS[self.op](len(match.matched_value), self.value)
```

Create `enforcer/predicates/string_matches.py`:

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match

@dataclass
class StringMatchesPredicate:
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return bool(re.search(self.pattern, match.matched_value))

@dataclass
class StringNotMatchesPredicate:
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return not bool(re.search(self.pattern, match.matched_value))
```

Create `enforcer/predicates/combinators.py`:

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class All:
    predicates: list

    def test(self, match) -> bool:
        return all(p.test(match) for p in self.predicates)

@dataclass
class Any:
    predicates: list

    def test(self, match) -> bool:
        return any(p.test(match) for p in self.predicates)

@dataclass
class NotP:
    predicate: object

    def test(self, match) -> bool:
        return not self.predicate.test(match)
```

Create `enforcer/predicates/__init__.py`:

```python
from enforcer.predicates.int_compare import IntPredicate
from enforcer.predicates.string_length import StringLengthPredicate
from enforcer.predicates.string_matches import StringMatchesPredicate, StringNotMatchesPredicate
from enforcer.predicates.combinators import All, Any, NotP

__all__ = [
    "IntPredicate",
    "StringLengthPredicate",
    "StringMatchesPredicate",
    "StringNotMatchesPredicate",
    "All",
    "Any",
    "NotP",
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_predicates/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/predicates/__init__.py enforcer/predicates/int_compare.py enforcer/predicates/string_length.py enforcer/predicates/string_matches.py enforcer/predicates/combinators.py tests/test_predicates/
git commit -m "feat: predicates (Int, StringLength, StringMatches) + predicate combinators"
```

---

## Task 7: Rule dataclass (check, message rendering, exclude_globs)

**Files:**
- Create: `enforcer/rule.py`
- Create: `tests/test_rule.py`
- Create: `tests/test_exclude_globs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rule.py`:

```python
import pytest
from enforcer import Severity, FileContext, Match
from enforcer.rule import Rule
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AnyOf, AllOf, Not
from enforcer.predicates import IntPredicate

def test_rule_basic():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message="Found {matched_value}",
    )
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    matches = rule.check(ctx, {})
    assert len(matches) == 1
    assert matches[0].rule_id == "test"
    assert matches[0].severity == Severity.ERROR
    assert matches[0].message == "Found #fff"

def test_rule_exclude_globs():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts"],
    )
    ctx = FileContext(path="foo.spec.ts", raw="color: #fff;")
    assert rule.check(ctx, {}) == []

def test_rule_exclude_globs_not_matching():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts"],
    )
    ctx = FileContext(path="foo.ts", raw="color: #fff;")
    matches = rule.check(ctx, {})
    assert len(matches) == 1

def test_rule_multiple_exclude_globs():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/generated/**", "**/material-theme*"],
    )
    assert rule.check(FileContext(path="x.spec.ts", raw="#fff"), {}) == []
    assert rule.check(FileContext(path="generated/y.ts", raw="#fff"), {}) == []
    assert rule.check(FileContext(path="material-theme.scss", raw="#fff"), {}) == []
    assert len(rule.check(FileContext(path="z.ts", raw="#fff"), {})) == 1

def test_rule_message_template():
    rule = Rule(
        id="test",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"\bconst\b")],
        file_globs=["**/*.ts"],
        message="'{matched_value}' in {file}:{line}",
    )
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    matches = rule.check(ctx, {})
    assert matches[0].message == "'const' in x.ts:1"

def test_rule_message_callable():
    rule = Rule(
        id="test",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message=lambda m: f"Color {m.matched_value} at line {m.line}",
    )
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    matches = rule.check(ctx, {})
    assert matches[0].message == "Color #fff at line 1"

def test_rule_fix_instruction():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message="test",
        fix_instruction="Replace with var(--color-primary).",
    )
    ctx = FileContext(path="x.ts", raw="#fff")
    matches = rule.check(ctx, {})
    assert matches[0].fix_instruction == "Replace with var(--color-primary)."

def test_rule_flat_list_implicit_allof():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"\bconst\b"), RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message="test",
    )
    ctx = FileContext(path="x.ts", raw="const #fff;")
    matches = rule.check(ctx, {})
    assert len(matches) == 2

    ctx = FileContext(path="x.ts", raw="let x = 1;")
    matches = rule.check(ctx, {})
    assert matches == []

def test_rule_explicit_combinator():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[AnyOf([RegexMatcher(r"#fff"), RegexMatcher(r"#000")])],
        file_globs=["**/*.ts"],
        message="Found {matched_value}",
    )
    ctx = FileContext(path="x.ts", raw="color: #000;")
    matches = rule.check(ctx, {})
    assert len(matches) == 1
    assert matches[0].matched_value == "#000"

def test_rule_predicates_applied():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"\d+")],
        file_globs=["**/*.ts"],
        predicates=[IntPredicate(op=">", value=10)],
        message="Magic number {matched_value}",
    )
    ctx = FileContext(path="x.ts", raw="a = 5; b = 42; c = 3;")
    matches = rule.check(ctx, {})
    assert len(matches) == 1
    assert matches[0].matched_value == "42"

def test_rule_all_matches_reported():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
        file_globs=["**/*.ts"],
        message="Found {matched_value}",
    )
    ctx = FileContext(path="x.ts", raw="#fff #000 #aaa #bbb #ccc")
    matches = rule.check(ctx, {})
    assert len(matches) == 5
```

Create `tests/test_exclude_globs.py`:

```python
from enforcer import Severity, FileContext
from enforcer.rule import Rule
from enforcer.matchers import RegexMatcher

def test_exclude_single_pattern():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts"],
    )
    assert rule.check(FileContext(path="a.spec.ts", raw="#fff"), {}) == []
    assert len(rule.check(FileContext(path="a.ts", raw="#fff"), {})) == 1

def test_exclude_directory():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/generated/**"],
    )
    assert rule.check(FileContext(path="generated/a.ts", raw="#fff"), {}) == []

def test_exclude_wildcard_prefix():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.scss"],
        exclude_globs=["**/material-theme*"],
    )
    assert rule.check(FileContext(path="material-theme.scss", raw="#fff"), {}) == []
    assert len(rule.check(FileContext(path="colors.scss", raw="#fff"), {})) == 1

def test_no_exclude_globs():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
    )
    assert len(rule.check(FileContext(path="a.spec.ts", raw="#fff"), {})) == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_rule.py tests/test_exclude_globs.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/rule.py`:

```python
from __future__ import annotations
import fnmatch
from dataclasses import dataclass, field
from typing import Callable
from enforcer.types import Severity, Match, FileContext, LLMConsequence
from enforcer.matchers.allowlist import AllowlistMatcher
from enforcer.combinators.core import AllOf
from enforcer.predicates.combinators import All as AllPred

def _is_combinator(obj) -> bool:
    return hasattr(obj, "matchers") and hasattr(obj, "find")

def _run_matcher(matcher, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
    if isinstance(matcher, AllowlistMatcher):
        return matcher.find(file_ctx, shared_ctx)
    return matcher.find(file_ctx)

@dataclass
class Rule:
    id: str
    severity: Severity
    matchers: list
    file_globs: list[str]
    exclude_globs: list[str] = field(default_factory=list)
    workspace: str | None = None
    read_targets: list[str] = field(default_factory=list)
    predicates: list = field(default_factory=list)
    message: str | Callable = ""
    fix_instruction: str = ""
    llm_consequence: LLMConsequence | None = None

    def check(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        if self._excluded(file_ctx.path):
            return []

        if len(self.matchers) == 1 and _is_combinator(self.matchers[0]):
            all_matches = _run_matcher(self.matchers[0], file_ctx, shared_ctx)
        else:
            combined = AllOf(self.matchers)
            all_matches = combined.find(file_ctx, shared_ctx)

        for pred in self.predicates:
            all_matches = [m for m in all_matches if pred.test(m)]

        for m in all_matches:
            m.rule_id = self.id
            m.severity = self.severity
            m.fix_instruction = self.fix_instruction
            m.message = self._render_message(m)

        return all_matches

    def _excluded(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pat) for pat in self.exclude_globs)

    def _render_message(self, match: Match) -> str:
        if callable(self.message):
            return self.message(match)
        return self.message.format(
            matched_value=match.matched_value,
            file=match.file,
            line=match.line,
            column=match.column,
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_rule.py tests/test_exclude_globs.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/rule.py tests/test_rule.py tests/test_exclude_globs.py
git commit -m "feat: Rule dataclass with combinators, predicates, exclude_globs"
```

---

## Task 8: Reporter (JSON + text output, exit codes)

**Files:**
- Create: `enforcer/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reporter.py`:

```python
import json
import pytest
from enforcer import Severity, Match
from enforcer.reporter import Reporter

def test_json_output_format():
    matches = [
        Match(file="x.ts", line=1, column=7, message="Raw hex", rule_id="no-raw-hex",
              severity=Severity.ERROR, fix_instruction="Use var(--color-*)"),
    ]
    output = Reporter(format="json").render(matches)
    data = json.loads(output)
    assert data["summary"]["total"] == 1
    assert data["summary"]["errors"] == 1
    assert data["issues"][0]["file"] == "x.ts"
    assert data["issues"][0]["line"] == 1
    assert data["issues"][0]["severity"] == "error"

def test_text_output_format():
    matches = [
        Match(file="x.ts", line=1, column=7, message="Raw hex", rule_id="no-raw-hex",
              severity=Severity.ERROR, fix_instruction="Use var(--color-*)"),
    ]
    output = Reporter(format="text").render(matches)
    assert "x.ts:1:7 [ERROR] no-raw-hex" in output
    assert "Raw hex" in output
    assert "Use var(--color-*)" in output

def test_json_with_llm_response():
    matches = [
        Match(file="README.md", line=0, message="Too long", rule_id="verbose-readme",
              severity=Severity.WARN, llm_response="Lines 45-80 are architecture details..."),
    ]
    output = Reporter(format="json").render(matches)
    data = json.loads(output)
    assert data["issues"][0]["llm_response"] == "Lines 45-80 are architecture details..."

def test_exit_code_no_errors():
    matches = [Match(file="x.ts", line=1, message="warn", severity=Severity.WARN)]
    assert Reporter().exit_code(matches) == 0

def test_exit_code_with_errors():
    matches = [Match(file="x.ts", line=1, message="err", severity=Severity.ERROR)]
    assert Reporter().exit_code(matches) == 1

def test_empty_json_output():
    output = Reporter(format="json").render([])
    data = json.loads(output)
    assert data["summary"]["total"] == 0
    assert data["issues"] == []

def test_text_empty_output():
    output = Reporter(format="text").render([])
    assert "No issues found" in output

def test_multiple_severities_sorted():
    matches = [
        Match(file="a.ts", line=1, message="info", severity=Severity.INFO, rule_id="r1"),
        Match(file="b.ts", line=1, message="error", severity=Severity.ERROR, rule_id="r2"),
        Match(file="c.ts", line=1, message="warn", severity=Severity.WARN, rule_id="r3"),
    ]
    output = Reporter(format="text").render(matches)
    error_pos = output.index("ERROR")
    warn_pos = output.index("WARN")
    info_pos = output.index("INFO")
    assert error_pos < warn_pos < info_pos

def test_json_summary_counts():
    matches = [
        Match(file="a.ts", line=1, severity=Severity.ERROR),
        Match(file="b.ts", line=1, severity=Severity.ERROR),
        Match(file="c.ts", line=1, severity=Severity.WARN),
        Match(file="d.ts", line=1, severity=Severity.INFO),
    ]
    data = json.loads(Reporter(format="json").render(matches))
    assert data["summary"]["total"] == 4
    assert data["summary"]["errors"] == 2
    assert data["summary"]["warnings"] == 1
    assert data["summary"]["info"] == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_reporter.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/reporter.py`:

```python
from __future__ import annotations
import json
from enforcer.types import Match, Severity

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}

class Reporter:
    def __init__(self, format: str = "text"):
        self.format = format

    def render(self, matches: list[Match]) -> str:
        if self.format == "json":
            return self._render_json(matches)
        return self._render_text(matches)

    def _render_json(self, matches: list[Match]) -> str:
        summary = self._summary(matches)
        issues = []
        for m in sorted(matches, key=lambda m: (_SEVERITY_ORDER.get(m.severity, 99), m.file, m.line)):
            issue = {
                "file": m.file,
                "line": m.line,
                "column": m.column,
                "rule_id": m.rule_id,
                "severity": m.severity.value,
                "message": m.message,
                "fix_instruction": m.fix_instruction,
            }
            if m.llm_response:
                issue["llm_response"] = m.llm_response
            issues.append(issue)
        return json.dumps({"summary": summary, "issues": issues}, indent=2)

    def _render_text(self, matches: list[Match]) -> str:
        if not matches:
            return "No issues found.\n"
        lines = []
        sorted_matches = sorted(matches, key=lambda m: (_SEVERITY_ORDER.get(m.severity, 99), m.file, m.line))
        for m in sorted_matches:
            sev = m.severity.value.upper()
            loc = f"{m.file}:{m.line}"
            if m.column:
                loc += f":{m.column}"
            lines.append(f"{loc} [{sev}] {m.rule_id}")
            lines.append(f"  {m.message}")
            if m.fix_instruction:
                lines.append(f"  Fix: {m.fix_instruction}")
            if m.llm_response:
                lines.append(f"  LLM: {m.llm_response}")
            lines.append("")
        summary = self._summary(matches)
        blocked = " Commit blocked." if summary["errors"] > 0 else ""
        lines.append(f"Summary: {summary['total']} issues ({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info).{blocked}")
        return "\n".join(lines) + "\n"

    def _summary(self, matches: list[Match]) -> dict:
        return {
            "total": len(matches),
            "errors": sum(1 for m in matches if m.severity == Severity.ERROR),
            "warnings": sum(1 for m in matches if m.severity == Severity.WARN),
            "info": sum(1 for m in matches if m.severity == Severity.INFO),
        }

    def exit_code(self, matches: list[Match]) -> int:
        return 1 if any(m.severity == Severity.ERROR for m in matches) else 0
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_reporter.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/reporter.py tests/test_reporter.py
git commit -m "feat: Reporter with JSON/text output and exit codes"
```

---

## Task 9: LLM Executor (mock provider, parallel, timeout, --no-llm)

**Files:**
- Create: `enforcer/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm.py`:

```python
import pytest
from unittest.mock import Mock, patch
from enforcer import Severity, FileContext, Match, LLMConsequence
from enforcer.matchers import LineCountMatcher
from enforcer.rule import Rule
from enforcer.llm import LLMExecutor

def test_llm_fires_on_rule_failure():
    mock_response = Mock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Lines 45-80 too verbose"}}]}
    with patch("httpx.post", return_value=mock_response):
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="skainet", model="test-model", prompt="Analyze verbosity."),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=30)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    assert matches[0].llm_response == "Lines 45-80 too verbose"

def test_llm_skipped_when_rule_passes():
    with patch("httpx.post") as mock_post:
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=200)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x"),
        )
        ctx = FileContext(path="README.md", raw="short file")
        matches = rule.check(ctx, {})
        assert matches == []
        mock_post.assert_not_called()

def test_llm_no_llm_flag():
    with patch("httpx.post") as mock_post:
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x"),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=30, enabled=False)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    mock_post.assert_not_called()
    assert len(matches) == 1
    assert matches[0].llm_response == ""

def test_llm_timeout():
    import httpx
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        rule = Rule(
            id="test", severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"], message="x",
            llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x", timeout=1),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=1)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    assert matches[0].llm_response == ""

def test_llm_construction():
    executor = LLMExecutor(concurrency=3, timeout=60)
    assert executor.concurrency == 3
    assert executor.timeout == 60
    assert executor.enabled is True
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_llm.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/llm.py`:

```python
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from enforcer.types import Match, FileContext, LLMConsequence

class LLMExecutor:
    def __init__(self, concurrency: int = 5, timeout: int = 30, enabled: bool = True):
        self.concurrency = concurrency
        self.timeout = timeout
        self.enabled = enabled

    def execute(self, matches: list[Match], consequence: LLMConsequence | None,
                file_ctx: FileContext) -> list[Match]:
        if not consequence or not self.enabled or not matches:
            return matches
        if not file_ctx.raw:
            return matches

        prompt = f"{consequence.prompt}\n\n--- FILE CONTENT ---\n{file_ctx.raw}"
        provider_config = self._get_provider_config(consequence.provider)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._call_llm, consequence, prompt, provider_config): m
                for m in matches
            }
            for future in as_completed(futures):
                match = futures[future]
                try:
                    match.llm_response = future.result()
                except Exception:
                    match.llm_response = ""

        return matches

    def _call_llm(self, consequence: LLMConsequence, prompt: str, provider_config: dict) -> str:
        import httpx
        try:
            resp = httpx.post(
                f"{provider_config['baseURL']}/chat/completions",
                headers=provider_config.get("headers", {}),
                json={
                    "model": consequence.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=consequence.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return ""

    def _get_provider_config(self, provider: str) -> dict:
        # In production, read from opencode.json. For now, return a default.
        # This will be wired up in the config loader task.
        return {
            "baseURL": "https://chat.model.tngtech.com/v1",
            "headers": {"X-User-Agent": "OpenCode"},
        }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_llm.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/llm.py tests/test_llm.py
git commit -m "feat: LLM Executor with parallel calls, timeout, --no-llm support"
```

---

## Task 10: FileContext builder (parse-once optimization)

**Files:**
- Create: `enforcer/parsers/__init__.py`
- Create: `enforcer/parsers/language.py`
- Create: `enforcer/parsers/tree_sitter.py`
- Create: `enforcer/context.py`
- Create: `tests/test_context.py`
- Create: `tests/test_parse_once.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_context.py`:

```python
import pytest
from enforcer import Needs
from enforcer.context import FileContextBuilder
from enforcer.matchers import RegexMatcher, LineCountMatcher
from enforcer.rule import Rule

def test_builder_provides_raw():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    ctx = builder.build("tests/fixtures/sample.ts")
    assert ctx.raw is not None
    assert ctx.path == "tests/fixtures/sample.ts"

def test_builder_aggregates_needs():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[LineCountMatcher(max_lines=10)],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.ts", rules)
    assert Needs.RAW in needs
```

Create `tests/test_parse_once.py`:

```python
import pytest
from unittest.mock import patch, mock_open
from enforcer import Severity
from enforcer.context import FileContextBuilder
from enforcer.matchers import RegexMatcher
from enforcer.rule import Rule

def test_file_read_once():
    """Multiple rules targeting same file -> file read exactly once."""
    mock_data = "const #fff;"
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="c", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    with patch("builtins.open", mock_open(read_data=mock_data)) as mock_file:
        builder.build("x.ts")
        builder.build("x.ts")  # second call should use cache
        # First call reads; second uses cache
        assert mock_file.call_count <= 1 or mock_file.call_count == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_context.py tests/test_parse_once.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementations**

Create `enforcer/parsers/__init__.py` (empty).

Create `enforcer/parsers/language.py`:

```python
from __future__ import annotations
import os
from enforcer.types import Needs

_EXT_TO_NEEDS = {
    ".ts": Needs.AST_TS,
    ".tsx": Needs.AST_TS,
    ".js": Needs.AST_TS,
    ".jsx": Needs.AST_TS,
    ".py": Needs.AST_PY,
    ".scss": Needs.AST_CSS,
    ".css": Needs.AST_CSS,
}

def language_for_path(path: str) -> Needs | None:
    ext = os.path.splitext(path)[1]
    return _EXT_TO_NEEDS.get(ext)
```

Create `enforcer/parsers/tree_sitter.py`:

```python
from __future__ import annotations
from enforcer.types import Needs

def parse(source: str, needs: Needs):
    """Parse source code into a tree-sitter tree.
    Returns None if tree-sitter is not available or language not supported."""
    try:
        import tree_sitter as ts
    except ImportError:
        return None

    language_map = {
        Needs.AST_TS: _get_ts_language,
        Needs.AST_PY: _get_py_language,
        Needs.AST_CSS: _get_css_language,
    }

    lang_func = language_map.get(needs)
    if not lang_func:
        return None

    language = lang_func()
    if not language:
        return None

    parser = ts.Parser()
    parser.language = language
    tree = parser.parse(bytes(source, "utf-8"))
    return tree

def _get_ts_language():
    try:
        import tree_sitter_typescript as ts_ts
        return ts_ts.language_typescript()
    except ImportError:
        return None

def _get_py_language():
    try:
        import tree_sitter_python as ts_py
        return ts_py.language()
    except ImportError:
        return None

def _get_css_language():
    try:
        import tree_sitter_css as ts_css
        return ts_css.language()
    except ImportError:
        return None
```

Create `enforcer/context.py`:

```python
from __future__ import annotations
import os
from enforcer.types import FileContext, Needs
from enforcer.parsers.language import language_for_path
from enforcer.parsers.tree_sitter import parse as ts_parse

class FileContextBuilder:
    def __init__(self, rules: list, workspace: str = "."):
        self.rules = rules
        self.workspace = workspace
        self._cache: dict[str, FileContext] = {}

    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext:
        if path in self._cache:
            return self._cache[path]

        full_path = os.path.join(self.workspace, path) if self.workspace else path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except (IOError, OSError):
            return FileContext(path=path, raw=None)

        ctx = FileContext(path=path, raw=raw)

        needs = force_needs or self.needs_for_file(path, self.rules)

        ast_need = None
        for n in needs:
            if n in (Needs.AST_TS, Needs.AST_PY, Needs.AST_CSS):
                ast_need = n
                break

        if ast_need:
            ctx.ast = ts_parse(raw, ast_need)

        self._cache[path] = ctx
        return ctx

    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        import fnmatch
        needs: set[Needs] = set()
        for rule in rules:
            if any(fnmatch.fnmatch(path, glob) for glob in rule.file_globs):
                if not any(fnmatch.fnmatch(path, pat) for pat in rule.exclude_globs):
                    for matcher in rule.matchers:
                        if hasattr(matcher, "needs") and matcher.needs:
                            needs.add(matcher.needs)
        return needs

    def clear_cache(self):
        self._cache.clear()
```

- [ ] **Step 4: Run tests**

```bash
# Create fixtures dir
mkdir -p tests/fixtures
echo 'const x = #fff;' > tests/fixtures/sample.ts

pytest tests/test_context.py tests/test_parse_once.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/parsers/__init__.py enforcer/parsers/language.py enforcer/parsers/tree_sitter.py enforcer/context.py tests/test_context.py tests/test_parse_once.py tests/fixtures/sample.ts
git commit -m "feat: FileContext builder with parse-once optimization"
```

---

## Task 11: Config loader

**Files:**
- Create: `enforcer/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
import pytest
import tempfile
import os
from enforcer.config import Config, load_config

def test_config_loads_rules():
    config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

WORKSPACE = "."
RULES = [
    Rule(
        id="test-rule",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message="Found hex",
    ),
]
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.workspace == "."
    assert len(config.rules) == 1
    assert config.rules[0].id == "test-rule"

def test_config_severity_actions():
    config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "print",
}
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.severity_actions[Severity.ERROR] == "block"

def test_config_default_workspace():
    config_content = '''
from enforcer import Rule, Severity
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.workspace == "."

def test_config_llm_config():
    config_content = '''
from enforcer import Rule, Severity
LLM_CONFIG = {"concurrency": 3, "timeout": 60}
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.llm_config["concurrency"] == 3
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_config.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/config.py`:

```python
from __future__ import annotations
import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any
from enforcer.types import Severity

@dataclass
class Config:
    rules: list = field(default_factory=list)
    workspace: str = "."
    severity_actions: dict = field(default_factory=dict)
    llm_config: dict = field(default_factory=dict)

def load_config(config_path: str) -> Config:
    spec = importlib.util.spec_from_file_location("enforcer_config", config_path)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load config from {config_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return Config(
        rules=getattr(module, "RULES", []),
        workspace=getattr(module, "WORKSPACE", "."),
        severity_actions=getattr(module, "SEVERITY_ACTIONS", {
            Severity.ERROR: "block",
            Severity.WARN: "print",
            Severity.INFO: "hint",
        }),
        llm_config=getattr(module, "LLM_CONFIG", {
            "concurrency": 5,
            "timeout": 30,
        }),
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/config.py tests/test_config.py
git commit -m "feat: config loader"
```

---

## Task 12: Rule Runner

**Files:**
- Create: `enforcer/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_runner.py`:

```python
import pytest
from enforcer import Severity, FileContext
from enforcer.runner import RuleRunner
from enforcer.matchers import RegexMatcher, LineCountMatcher
from enforcer.rule import Rule

def test_runner_collects_all_matches():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
             file_globs=["**/*.ts"], message="Found {matched_value}"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff #000 #aaa")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 3

def test_runner_multiple_rules():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="hex"),
        Rule(id="lines", severity=Severity.WARN,
             matchers=[LineCountMatcher(max_lines=2)],
             file_globs=["**/*.ts"], message="too long"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff\nline2\nline3\n")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 2
    rule_ids = {m.rule_id for m in matches}
    assert rule_ids == {"hex", "lines"}

def test_runner_respects_file_globs():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.scss"], message="hex"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff")
    matches = runner.run_rules_for_file(ctx, {})
    assert matches == []

def test_runner_respects_exclude_globs():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"],
             exclude_globs=["**/*.spec.ts"],
             message="hex"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.spec.ts", raw="#fff")
    matches = runner.run_rules_for_file(ctx, {})
    assert matches == []

def test_runner_no_llm():
    from enforcer import LLMConsequence
    rules = [
        Rule(id="lines", severity=Severity.WARN,
             matchers=[LineCountMatcher(max_lines=2)],
             file_globs=["**/*.ts"], message="x",
             llm_consequence=LLMConsequence(provider="p", model="m", prompt="x")),
    ]
    runner = RuleRunner(rules, workspace=".", no_llm=True)
    ctx = FileContext(path="x.ts", raw="line1\nline2\nline3\n")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 1
    assert matches[0].llm_response == ""

def test_runner_filter_by_severity():
    rules = [
        Rule(id="warn", severity=Severity.WARN,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="w"),
        Rule(id="err", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#000")],
             file_globs=["**/*.ts"], message="e"),
    ]
    runner = RuleRunner(rules, workspace=".", min_severity=Severity.ERROR)
    ctx = FileContext(path="x.ts", raw="#fff #000")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 1
    assert matches[0].rule_id == "err"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_runner.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/runner.py`:

```python
from __future__ import annotations
import fnmatch
from enforcer.types import Severity, Match, FileContext
from enforcer.rule import Rule
from enforcer.llm import LLMExecutor

_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}

class RuleRunner:
    def __init__(self, rules: list[Rule], workspace: str = ".",
                 no_llm: bool = False, min_severity: Severity = Severity.INFO,
                 llm_config: dict | None = None):
        self.rules = rules
        self.workspace = workspace
        self.min_severity = min_severity
        llm_config = llm_config or {"concurrency": 5, "timeout": 30}
        self.llm_executor = LLMExecutor(
            concurrency=llm_config.get("concurrency", 5),
            timeout=llm_config.get("timeout", 30),
            enabled=not no_llm,
        )

    def run_rules_for_file(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        all_matches: list[Match] = []
        for rule in self.rules:
            if not self._file_matches(file_ctx.path, rule):
                continue
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            matches = rule.check(file_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, file_ctx)
            all_matches.extend(matches)
        return all_matches

    def _file_matches(self, path: str, rule: Rule) -> bool:
        if not any(fnmatch.fnmatch(path, glob) for glob in rule.file_globs):
            return False
        if any(fnmatch.fnmatch(path, pat) for pat in rule.exclude_globs):
            return False
        return True

    def run(self, file_contexts: list[FileContext], shared_ctx: dict) -> list[Match]:
        all_matches: list[Match] = []
        for ctx in file_contexts:
            matches = self.run_rules_for_file(ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_runner.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/runner.py tests/test_runner.py
git commit -m "feat: RuleRunner with severity filtering and LLM integration"
```

---

## Task 13: CLI

**Files:**
- Create: `enforcer/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli.py`:

```python
import json
import pytest
from unittest.mock import patch, Mock
from click.testing import CliRunner
from enforcer.cli import cli

@pytest.fixture
def runner():
    return CliRunner()

def test_cli_staged(runner):
    with patch("subprocess.check_output", return_value=b"x.ts\ny.ts\n"), \
         patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--staged", "--format", "json"])
        assert result.exit_code == 0

def test_cli_all(runner):
    with patch("os.walk", return_value=[(".", [], ["x.ts", "y.ts"])]), \
         patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--all"])
        assert result.exit_code == 0

def test_cli_paths(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "y.ts"])
        assert result.exit_code == 0

def test_cli_workspace(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--workspace", "frontend/", "--paths", "x.ts"])
        assert result.exit_code == 0

def test_cli_format_json(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--format", "json"])
        data = json.loads(result.output)
        assert "summary" in data
        assert "issues" in data

def test_cli_format_text(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--format", "text"])
        assert result.exit_code == 0

def test_cli_no_llm(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--no-llm"])
        assert result.exit_code == 0

def test_cli_exit_code_on_error(runner):
    from enforcer import Severity, Match
    match = Match(file="x.ts", line=1, message="err", severity=Severity.ERROR)
    with patch("enforcer.runner.RuleRunner.run", return_value=[match]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts"])
        assert result.exit_code == 1

def test_cli_exit_code_on_warn_only(runner):
    from enforcer import Severity, Match
    match = Match(file="x.ts", line=1, message="warn", severity=Severity.WARN)
    with patch("enforcer.runner.RuleRunner.run", return_value=[match]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts"])
        assert result.exit_code == 0

def test_cli_config_path(runner):
    with patch("enforcer.runner.RuleRunner.run", return_value=[]):
        result = runner.invoke(cli, ["check", "--config", "custom_config.py", "--paths", "x.ts"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_cli.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementation**

Create `enforcer/cli.py`:

```python
from __future__ import annotations
import os
import subprocess
import sys
import click
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter

@click.group()
def cli():
    """Convention enforcement tool for coding agents."""
    pass

@cli.command()
@click.option("--staged", is_flag=True, help="Check staged files only")
@click.option("--all", "all_files", is_flag=True, help="Check entire repo")
@click.option("--paths", multiple=True, help="Check specific files")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]))
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--workspace", default=None, help="Global workspace root")
@click.option("--severity", default="info", type=click.Choice(["error", "warn", "info"]))
@click.option("--no-llm", is_flag=True, help="Skip LLM consequences")
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm):
    """Check files for convention violations."""
    from enforcer.types import Severity

    config = load_config(config_path)
    ws = workspace or config.workspace

    if staged:
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            stderr=subprocess.DEVNULL,
        )
        file_list = result.decode().strip().split("\n") if result.strip() else []
    elif all_files:
        file_list = []
        for root, dirs, files in os.walk(ws):
            if ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
    elif paths:
        file_list = list(paths)
    else:
        file_list = []

    sev_map = {"error": Severity.ERROR, "warn": Severity.WARN, "info": Severity.INFO}

    runner = RuleRunner(
        config.rules,
        workspace=ws,
        no_llm=no_llm,
        min_severity=sev_map[severity],
        llm_config=config.llm_config,
    )

    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                target_ctx = builder.build(target.replace("**/", ""))
                shared_ctx[os.path.basename(target_path)] = target_ctx

    all_matches = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    reporter = Reporter(format=fmt)
    output = reporter.render(all_matches)
    click.echo(output)
    sys.exit(reporter.exit_code(all_matches))

if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cli.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enforcer/cli.py tests/test_cli.py
git commit -m "feat: CLI with check command"
```

---

## Task 14: Integration test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write test**

Create `tests/test_integration.py`:

```python
import os
import re
import pytest
from enforcer import Severity
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter
from enforcer.matchers import RegexMatcher, LineCountMatcher, AllowlistMatcher
from enforcer.rule import Rule

def test_full_run_on_fixture_repo(tmp_path):
    """End-to-end: fixture repo with known violations."""
    (tmp_path / "colors.scss").write_text("--color-primary: #fff;\n--color-secondary: #000;\n")
    (tmp_path / "component.ts").write_text(
        "background: #c8e6c9;\n"
        "color: var(--color-primary);\n"
        "border: var(--color-undefined);\n"
    )
    (tmp_path / "component.spec.ts").write_text("background: #fff;\n")
    (tmp_path / "README.md").write_text("\n".join(["line"] * 250))

    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts", "**/*.scss"],
            exclude_globs=["**/*.spec.ts", "**/colors.scss"],
            read_targets=["**/colors.scss"],
            message="Raw hex '{matched_value}'",
        ),
        Rule(
            id="only-defined-css-vars",
            severity=Severity.ERROR,
            matchers=[AllowlistMatcher(
                extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
                consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
                read_target="**/colors.scss",
            )],
            file_globs=["**/*.ts"],
            read_targets=["**/colors.scss"],
            message="Undefined: --{matched_value}",
        ),
        Rule(
            id="max-lines",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=200)],
            file_globs=["README.md"],
            message="{matched_value} lines",
        ),
    ]

    builder = FileContextBuilder(rules, workspace=str(tmp_path))
    shared_ctx = {}
    colors_path = os.path.join(str(tmp_path), "colors.scss")
    if os.path.exists(colors_path):
        ctx = builder.build("colors.scss")
        shared_ctx["colors.scss"] = ctx

    runner = RuleRunner(rules, workspace=str(tmp_path), no_llm=True)
    all_matches = []
    for f in ["colors.scss", "component.ts", "component.spec.ts", "README.md"]:
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    hex_matches = [m for m in all_matches if m.rule_id == "no-raw-hex"]
    assert len(hex_matches) == 1
    assert hex_matches[0].matched_value == "#c8e6c9"

    var_matches = [m for m in all_matches if m.rule_id == "only-defined-css-vars"]
    assert len(var_matches) == 1
    assert var_matches[0].matched_value == "color-undefined"

    spec_matches = [m for m in all_matches if ".spec." in m.file]
    assert spec_matches == []

    readme_matches = [m for m in all_matches if m.rule_id == "max-lines"]
    assert len(readme_matches) == 1

    assert Reporter().exit_code(all_matches) == 1

def test_full_run_clean_repo(tmp_path):
    """No violations -> exit 0."""
    (tmp_path / "component.ts").write_text("color: var(--color-primary);\n")
    (tmp_path / "colors.scss").write_text("--color-primary: #fff;\n")

    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts"],
            exclude_globs=["**/colors.scss"],
            message="Raw hex",
        ),
    ]

    builder = FileContextBuilder(rules, workspace=str(tmp_path))
    runner = RuleRunner(rules, workspace=str(tmp_path), no_llm=True)
    all_matches = []
    for f in ["component.ts", "colors.scss"]:
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, {})
        all_matches.extend(matches)

    assert all_matches == []
    assert Reporter().exit_code(all_matches) == 0
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_integration.py -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for end-to-end enforcement"
```

---

## Task 15: AstNodeMatcher + CommentPerFunctionMatcher (tree-sitter)

**Files:**
- Create: `enforcer/matchers/ast_node.py`
- Create: `enforcer/matchers/comment_density.py`
- Create: `tests/test_matchers/test_ast_node_matcher.py`
- Create: `tests/test_matchers/test_comment_density_matcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_matchers/test_ast_node_matcher.py`:

```python
import pytest
from enforcer import FileContext
from enforcer.matchers import AstNodeMatcher

def test_ast_finds_literal_expressions():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = "const x = 42;\nconst y = 100;\n"
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = AstNodeMatcher(node_type="literal_expression")
    matches = matcher.find(ctx)
    assert len(matches) == 2
    assert matches[0].matched_value == "42"
    assert matches[1].matched_value == "100"

def test_ast_finds_by_line():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = "const x = 42;\n"
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = AstNodeMatcher(node_type="literal_expression")
    matches = matcher.find(ctx)
    assert matches[0].line == 1
```

Create `tests/test_matchers/test_comment_density_matcher.py`:

```python
import pytest
from enforcer import FileContext
from enforcer.matchers import CommentPerFunctionMatcher

def test_comment_density_basic():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = """
function foo() {
    // comment 1
    // comment 2
    // comment 3
    // comment 4
    return 1;
}
function bar() {
    // only one
    return 2;
}
"""
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = CommentPerFunctionMatcher(max_comments=3)
    matches = matcher.find(ctx)
    # foo has 4 comments (>3), bar has 1 (<=3)
    assert len(matches) == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/test_matchers/test_ast_node_matcher.py tests/test_matchers/test_comment_density_matcher.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write implementations**

Create `enforcer/matchers/ast_node.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AstNodeMatcher:
    node_type: str
    scope: str | None = None
    needs: Needs | None = None

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk(root, scope=self.scope):
            if node.type == self.node_type:
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=node.text.decode(),
                ))
        return matches

    def _walk(self, node, scope=None):
        result = []
        if scope:
            for child in node.children:
                if self._is_scope_node(child, scope):
                    result.extend(self._walk_all(child))
                else:
                    result.extend(self._walk(child, scope=scope))
        else:
            result.extend(self._walk_all(node))
        return result

    def _is_scope_node(self, node, scope: str) -> bool:
        type_map = {
            "class": {"class_declaration", "class_definition", "class"},
            "function": {"function_declaration", "function_definition", "function",
                         "method_definition", "function_declaration"},
            "module": {"program"},
        }
        return node.type in type_map.get(scope, set())

    def _walk_all(self, node):
        yield node
        for child in node.children:
            yield from self._walk_all(child)
```

Create `enforcer/matchers/comment_density.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommentPerFunctionMatcher:
    max_comments: int
    needs: Needs | None = None

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in self._find_functions(root):
            comment_count = self._count_comments(func_node)
            if comment_count > self.max_comments:
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=str(comment_count),
                ))
        return matches

    def _find_functions(self, node):
        func_types = {"function_declaration", "function_definition", "function",
                       "method_definition", "method_declaration"}
        result = []
        for child in node.children:
            if child.type in func_types:
                result.append(child)
            result.extend(self._find_functions(child))
        return result

    def _count_comments(self, func_node) -> int:
        count = 0
        for node in self._walk_all(func_node):
            if "comment" in node.type:
                count += 1
        return count

    def _walk_all(self, node):
        yield node
        for child in node.children:
            yield from self._walk_all(child)
```

Update `enforcer/matchers/__init__.py`:

```python
from enforcer.matchers.regex import RegexMatcher
from enforcer.matchers.line_count import LineCountMatcher
from enforcer.matchers.char_count import CharCountMatcher
from enforcer.matchers.path_pattern import PathNotMatchingMatcher
from enforcer.matchers.allowlist import AllowlistMatcher
from enforcer.matchers.ast_node import AstNodeMatcher
from enforcer.matchers.comment_density import CommentPerFunctionMatcher

__all__ = [
    "RegexMatcher",
    "LineCountMatcher",
    "CharCountMatcher",
    "PathNotMatchingMatcher",
    "AllowlistMatcher",
    "AstNodeMatcher",
    "CommentPerFunctionMatcher",
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matchers/test_ast_node_matcher.py tests/test_matchers/test_comment_density_matcher.py -v
```
Expected: pass (or skip if tree-sitter not installed).

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/ast_node.py enforcer/matchers/comment_density.py enforcer/matchers/__init__.py tests/test_matchers/test_ast_node_matcher.py tests/test_matchers/test_comment_density_matcher.py
git commit -m "feat: AstNodeMatcher + CommentPerFunctionMatcher"
```

---

## Task 16: MCP server + example config

**Files:**
- Create: `enforcer/mcp_server.py`
- Create: `enforcer_config.py` (example)

- [ ] **Step 1: Write MCP server**

Create `enforcer/mcp_server.py`:

```python
from __future__ import annotations
import json
import sys
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter

def check_conventions(paths: list[str] | None = None, format: str = "json") -> str:
    """Run convention checks. Returns formatted output."""
    config = load_config("enforcer_config.py")
    ws = config.workspace

    if not paths:
        import subprocess
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            stderr=subprocess.DEVNULL,
        )
        file_list = result.decode().strip().split("\n") if result.strip() else []
    else:
        file_list = paths

    runner = RuleRunner(config.rules, workspace=ws, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            import os
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                ctx = builder.build(target.replace("**/", ""))
                shared_ctx[os.path.basename(target_path)] = ctx

    all_matches = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    reporter = Reporter(format=format)
    return reporter.render(all_matches)

def run_mcp_server():
    """Minimal stdio JSON-RPC server for MCP protocol."""
    for line in sys.stdin:
        try:
            msg = json.loads(line)
            if msg.get("method") == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "tools": [{
                            "name": "check_conventions",
                            "description": "Check files for convention violations",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "format": {"type": "string", "enum": ["json", "text"]},
                                },
                            },
                        }]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif msg.get("method") == "tools/call":
                params = msg.get("params", {})
                args = params.get("arguments", {})
                result = check_conventions(
                    paths=args.get("paths"),
                    format=args.get("format", "json"),
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {"content": [{"type": "text", "text": result}]}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if "msg" in dir() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
```

- [ ] **Step 2: Create example config**

Create `enforcer_config.py`:

```python
import re
from enforcer import (
    Rule, Severity, LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher, LineCountMatcher, PathNotMatchingMatcher,
    AllowlistMatcher,
)
from enforcer.combinators import AnyOf, AllOf, Not
from enforcer.predicates import IntPredicate

WORKSPACE = "."

RULES = [
    Rule(
        id="no-raw-hex",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
        file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
        exclude_globs=["**/*.spec.ts", "**/material-theme.scss", "**/generated/**"],
        workspace="frontend/",
        read_targets=["**/colors.scss"],
        message="Raw hex color '{matched_value}' found. Use var(--color-*) from colors.scss.",
        fix_instruction="Replace with the appropriate var(--color-*) from colors.scss.",
    ),
    Rule(
        id="max-lines-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=200)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 200).",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "print",
    Severity.INFO: "hint",
}

LLM_CONFIG = {
    "concurrency": 5,
    "timeout": 30,
}
```

- [ ] **Step 3: Verify everything runs together**

```bash
# Create a test file with a violation
echo 'const x = "#fff";' > /tmp/test_violation.ts

# Run enforcer
python -m enforcer.cli check --paths /tmp/test_violation.ts --config enforcer_config.py --format text --no-llm

# Run full test suite
pytest -v
```
Expected: all tests pass, CLI outputs violation.

- [ ] **Step 4: Commit**

```bash
git add enforcer/mcp_server.py enforcer_config.py
git commit -m "feat: MCP server + example config"
```

---

## Task 17: Full test suite + final commit

- [ ] **Step 1: Run full test suite**

```bash
pytest -v --cov=enforcer --cov-report=term-missing
```
Expected: all pass, coverage > 80%.

- [ ] **Step 2: Fix any failing tests**

Address any issues found in step 1.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: full test suite passing"
```
