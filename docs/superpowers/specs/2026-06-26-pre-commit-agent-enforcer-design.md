# Design Spec: Pre-Commit Agent Enforcer

**Date:** 2026-06-26
**Status:** Draft — pending user review
**Approach:** B — Standalone CLI + MCP server, pre-commit hook as thin wrapper

---

## 1. Overview

A Python tool (`enforcer`) that deterministically detects deviations from
project conventions and prevents agents from committing them. Rules are written
as code (regex + AST-based). Each file is parsed exactly once regardless of how
many rules target it. Output is JSON or text, printed to stdout on every run.

When a deterministic rule fails, an optional LLM consequence can fire: the
rule provides file content + a prompt, the LLM returns a localized verdict that
is included in the output as the fix instruction.

### Goals

- Deterministic convention enforcement (regex + AST)
- Cross-file context via read targets
- Single output with ALL issues (no back-and-forth)
- Configurable severity (error blocks commit, warn prints, info hints)
- LLM-backed investigation as a consequence of rule failure (not the rule itself)
- Agent self-check via MCP server
- Parse-once: file read/parsed exactly once, shared across all rules

### Non-goals

- Auto-fixing code (fix instructions are text only)
- Replacing existing linters (ruff, eslint, stylelint)
- Caching LLM responses (YAGNI — add later if needed)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   enforcer (CLI)                     │
│                                                     │
│  enforcer check [--staged|--all|--paths FILE...]    │
│                 [--format json|text]                 │
│                 [--config enforcer_config.py]        │
│                 [--workspace PATH]                   │
│                                                     │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────┐ │
│  │ Config Loader│──>│ Rule Runner  │──>│ Reporter │ │
│  └─────────────┘   └──────────────┘   └──────────┘ │
│         │                  │                  │      │
│         │           ┌──────┴───────┐          │      │
│         │           │ FileContext   │          │      │
│         │           │ Builder      │          │      │
│         │           └──────┬───────┘          │      │
│         │                  │                  │      │
│         │           ┌──────┴───────┐          │      │
│         │           │ LLM Executor  │          │      │
│         │           │ (parallel)   │          │      │      │
│         │           └──────────────┘          │      │
│  ┌─────────────┐                               │      │
│  │ MCP Server   │                              │      │
│  │ (enforcer    │                              │      │
│  │  mcp)        │                               │      │
│  └─────────────┘                               │      │
└─────────────────────────────────────────────────────┘
```

### Components

| Component | Responsibility |
|-----------|---------------|
| **Config Loader** | Loads `enforcer_config.py`, instantiates rules, resolves read targets |
| **FileContext Builder** | Reads each file once, parses to AST (tree-sitter) or keeps raw text. Groups rules by file + declared needs. Optimizes parse passes. |
| **Rule Runner** | Executes rules against FileContext. Collects all matches (not just first). Runs deterministic rules first, then triggers LLM consequences for failures. |
| **LLM Executor** | Parallel LLM calls (concurrency cap, default 5) via OpenAI-compatible API. Only fires when a deterministic rule fails AND declares an LLM consequence. |
| **Reporter** | Formats output as JSON or text. Prints to stdout. Exit code: non-zero if any error-severity issues. |
| **MCP Server** | Exposes `check_conventions` tool. Agent calls proactively. Returns same JSON. |

---

## 3. Rule Model — Composable DSL

### 3.1 Design principles

Every rule decomposes into: **matchers** (find things in file) + **predicates**
(filter matches) + **consequences** (report/LLM). The DSL provides reusable
building blocks for each. Rules compose them declaratively — no subclassing
for 90% of cases. A `Rule` subclass remains as an escape hatch for complex
logic that the DSL can't express.

### 3.2 Core types

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Pattern

class Severity(Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"

class Needs(Enum):
    RAW = "raw"
    AST_TS = "ast_ts"
    AST_PY = "ast_py"
    AST_CSS = "ast_css"
    # PATH implicitly always available

@dataclass
class Match:
    file: str
    line: int            # 1-indexed, 0 = file-level
    column: int = 0      # 1-indexed, 0 = line-level
    message: str = ""
    rule_id: str = ""
    severity: Severity = Severity.WARN
    fix_instruction: str = ""
    llm_response: str = ""
    # Internal: extracted value from matcher (e.g. matched text, node value)
    matched_value: str = ""

@dataclass
class FileContext:
    path: str
    raw: str | None = None
    ast: object | None = None  # tree-sitter Tree

@dataclass
class LLMConsequence:
    provider: str
    model: str
    prompt: str
    timeout: int = 30
    # file_ctx.raw automatically included as context
```

### 3.3 Matchers

Matchers are reusable functions that find things in a `FileContext`. Each
matcher returns a list of `Match` objects (with location + matched_value set).
Rules compose matchers, add predicates, set messages.

```python
# ── Regex matcher ──────────────────────────────────────────────
@dataclass
class RegexMatcher:
    """Find all regex matches in raw text. Returns Match per hit."""
    pattern: str | Pattern
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        import re
        matches = []
        for i, line in enumerate(file_ctx.raw.splitlines(), 1):
            for m in re.finditer(self.pattern, line):
                matches.append(Match(
                    file=file_ctx.path,
                    line=i,
                    column=m.start() + 1,
                    matched_value=m.group(),
                ))
        return matches

# ── AST node matcher ───────────────────────────────────────────
@dataclass
class AstNodeMatcher:
    """Find AST nodes by type + scope. Returns Match per node."""
    node_type: str          # tree-sitter node type, e.g. "literal_expression"
    scope: str = None       # "class", "function", "module", None = any
    needs: Needs = None     # inferred from language, or explicit

    def find(self, file_ctx: FileContext) -> list[Match]:
        matches = []
        tree = file_ctx.ast
        for node in self._walk(tree, scope=self.scope):
            if node.type == self.node_type:
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=node.text.decode(),
                ))
        return matches

    def _walk(self, tree, scope=None):
        # Walk tree-sitter tree, optionally filtering by scope
        # scope="class" → only nodes inside class bodies
        # scope="function" → only nodes inside function bodies
        ...

# ── Line count matcher ─────────────────────────────────────────
@dataclass
class LineCountMatcher:
    """Returns single Match if line count exceeds threshold."""
    max_lines: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        count = len(file_ctx.raw.splitlines())
        if count > self.max_lines:
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=str(count),
            )]
        return []

# ── Char count matcher ─────────────────────────────────────────
@dataclass
class CharCountMatcher:
    """Returns single Match if char count exceeds threshold."""
    max_chars: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        count = len(file_ctx.raw)
        if count > self.max_chars:
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=str(count),
            )]
        return []

# ── Path pattern matcher ───────────────────────────────────────
@dataclass
class PathNotMatchingMatcher:
    """Returns single Match if file path does NOT match the pattern."""
    pattern: str
    needs: Needs = Needs.PATH  # only needs path, no content read

    def find(self, file_ctx: FileContext) -> list[Match]:
        import fnmatch
        if not fnmatch.fnmatch(file_ctx.path, self.pattern):
            return [Match(file=file_ctx.path, line=0, matched_value=file_ctx.path)]
        return []

# ── Comment density matcher (AST) ──────────────────────────────
@dataclass
class CommentPerFunctionMatcher:
    """Returns Match per function where comment lines exceed threshold."""
    max_comments: int
    needs: Needs = None  # AST, language-inferred

    def find(self, file_ctx: FileContext) -> list[Match]:
        # Walk AST, find function definitions, count comment nodes in each
        ...

# ── Cross-file allowlist matcher ───────────────────────────────
@dataclass
class AllowlistMatcher:
    """Find items in file that are NOT in the allowlist (from read_targets).
    Uses extractor functions to pull items from both files."""
    extractor: Callable[[str], set[str]]     # extracts allowed items from target file
    consumer: Callable[[str], set[str]]       # extracts used items from checked file
    read_target: str                          # glob for allowlist source
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        target_ctx = shared_ctx.get(self._basename(self.read_target))
        if not target_ctx:
            return []
        allowed = self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        undefined = used - allowed
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=item,
        ) for item in undefined]
```

### 3.4 Logical combinators

Matchers can be combined with logical operators. A combinator wraps matchers
and controls whether the rule fires + which matches are reported.

**Semantics:** Each matcher returns `list[Match]`. Combinators return
`list[Match]` — empty list = "no match" (rule doesn't fire for this file).

```python
# ── AllOf (AND) ────────────────────────────────────────────────
@dataclass
class AllOf:
    """All matchers must produce ≥1 match. Reports all matches from all.
    This is the default when matchers= is a flat list."""
    matchers: list

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        results = [self._run(m, file_ctx, shared_ctx) for m in self.matchers]
        if all(r for r in results):          # all non-empty
            return [m for r in results for m in r]
        return []

# ── AnyOf (OR) ─────────────────────────────────────────────────
@dataclass
class AnyOf:
    """At least one matcher must produce ≥1 match. Reports matches from
    all matchers that produced results."""
    matchers: list

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        results = [self._run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return [m for r in results if r for m in r]
        return []

# ── OneOf (XOR) ────────────────────────────────────────────────
@dataclass
class OneOf:
    """Exactly one matcher must produce ≥1 match. Reports matches from
    that one matcher. If 0 or 2+ matchers produce results, returns empty."""
    matchers: list

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        results = [self._run(m, file_ctx, shared_ctx) for m in self.matchers]
        non_empty = [r for r in results if r]
        if len(non_empty) == 1:
            return non_empty[0]
        return []

# ── Not (negation) ─────────────────────────────────────────────
@dataclass
class Not:
    """Matcher must produce ZERO matches. If it does, returns empty.
    If it doesn't, returns a single file-level Match (the thing was absent).
    Useful for 'must contain X' / 'must not contain X' rules."""
    matcher: object
    message_on_absence: str = "Expected pattern not found."

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        results = self._run(self.matcher, file_ctx, shared_ctx)
        if results:
            return []    # matcher found things → Not fails → no match
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(absent)",
            message=self.message_on_absence,
        )]

# ── NoneOf (NOR) ───────────────────────────────────────────────
@dataclass
class NoneOf:
    """No matcher may produce any matches. If all are empty, returns a
    single file-level Match. If any produces matches, returns empty."""
    matchers: list
    message_on_absence: str = "All forbidden patterns absent."

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        results = [self._run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return []    # at least one found something → NoneOf fails
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(all absent)",
            message=self.message_on_absence,
        )]

# Helper: run a matcher or combinator (duck-typed)
def _run(matcher, file_ctx, shared_ctx):
    if isinstance(matcher, AllowlistMatcher):
        return matcher.find(file_ctx, shared_ctx)
    return matcher.find(file_ctx)
```

Combinators can be nested: `AllOf([AnyOf([A, B]), Not(C)])` means
"(A or B) and (not C)".

**Flat list shorthand:** `matchers=[A, B, C]` is equivalent to
`matchers=[AllOf([A, B, C])]`. The Rule.check method detects whether the
single element is a combinator or a flat list of matchers.

### 3.5 Predicates

Predicates filter `Match` objects returned by matchers. They refine which
matches are reported.

```python
@dataclass
class IntPredicate:
    """Filter matches where matched_value as int satisfies comparison."""
    op: str       # ">", "<", ">=", "<=", "==", "!="
    value: int

    def test(self, match: Match) -> bool:
        try:
            val = int(match.matched_value)
        except ValueError:
            return False
        return {
            ">": val > self.value,
            "<": val < self.value,
            ">=": val >= self.value,
            "<=": val <= self.value,
            "==": val == self.value,
            "!=": val != self.value,
        }[self.op]

@dataclass
class StringLengthPredicate:
    """Filter matches where matched_value string length satisfies comparison."""
    op: str
    value: int

    def test(self, match: Match) -> bool:
        length = len(match.matched_value)
        return {
            ">": length > self.value,
            "<": length < self.value,
            ">=": length >= self.value,
            "<=": length <= self.value,
            "==": length == self.value,
        }[self.op]

@dataclass
class StringMatchesPredicate:
    """Filter matches where matched_value matches a regex."""
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        import re
        return bool(re.search(self.pattern, match.matched_value))

@dataclass
class StringNotMatchesPredicate:
    """Filter matches where matched_value does NOT match a regex."""
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        import re
        return not bool(re.search(self.pattern, match.matched_value))
```

Predicates can also be combined with logical operators:

```python
# Custom predicate combinators
@dataclass
class All:    # AND
    predicates: list
    def test(self, match): return all(p.test(match) for p in self.predicates)

@dataclass
class Any:    # OR
    predicates: list
    def test(self, match): return any(p.test(match) for p in self.predicates)

@dataclass
class NotP:  # NOT
    predicate: object
    def test(self, match): return not self.predicate.test(match)
```

### 3.6 Rule (composable)

A rule composes matchers (or combinators), predicates, and a message template.
This is the 90% case — no subclassing needed.

```python
@dataclass
class Rule:
    id: str
    severity: Severity
    matchers: list                           # list of Matchers and/or Combinators
    file_globs: list[str]                    # include patterns
    exclude_globs: list[str] = field(default_factory=list)  # exclude patterns (exceptions)
    workspace: str | None = None             # None = global workspace
    read_targets: list[str] = field(default_factory=list)
    predicates: list = field(default_factory=list)  # applied to all matches
    message: str | Callable = ""             # str with {matched_value}, {file}, {line} or callable
    fix_instruction: str = ""
    llm_consequence: LLMConsequence | None = None

    def check(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        # Check exclude_globs first — if file matches any, skip rule entirely
        if self._excluded(file_ctx.path):
            return []
        # Detect flat matcher list vs combinator
        if len(self.matchers) == 1 and hasattr(self.matchers[0], 'matchers'):
            # Single combinator — run it
            all_matches = self._run(self.matchers[0], file_ctx, shared_ctx)
        else:
            # Flat list → implicit AllOf (AND)
            all_matches = AllOf(self.matchers).find(file_ctx, shared_ctx)
        # Apply predicates
        for pred in self.predicates:
            all_matches = [m for m in all_matches if pred.test(m)]
        # Set rule metadata on each match
        for m in all_matches:
            m.rule_id = self.id
            m.severity = self.severity
            m.fix_instruction = self.fix_instruction
            m.message = self._render_message(m)
        return all_matches

    def _excluded(self, path: str) -> bool:
        """Return True if path matches any exclude_glob."""
        import fnmatch
        return any(fnmatch.fnmatch(path, pat) for pat in self.exclude_globs)

    def _run(self, matcher, file_ctx, shared_ctx):
        """Duck-typed matcher/combinator runner."""
        if isinstance(matcher, AllowlistMatcher):
            return matcher.find(file_ctx, shared_ctx)
        return matcher.find(file_ctx)

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

### 3.7 Glob exceptions (`exclude_globs`)

A rule can exclude specific files or patterns from matching. This is separate
from `file_globs` (which defines what's included):

```python
Rule(
    id="no-raw-hex",
    severity=Severity.ERROR,
    matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
    file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
    exclude_globs=[                # exceptions — these files are NOT checked
        "**/*.spec.ts",            # test files
        "**/material-theme.scss",  # Material theme definitions use raw hex
        "**/generated/**",         # generated code
    ],
    workspace="frontend/",
    message="Raw hex color '{matched_value}' found. Use var(--color-*) from colors.scss.",
)
```

`exclude_globs` supports the same fnmatch patterns as `file_globs`. A file is
checked only if it matches at least one `file_globs` pattern AND does NOT match
any `exclude_globs` pattern.

### 3.8 Rule examples (DSL)

**No raw hex (with exclude_globs):**
```python
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
)
```

**Magic number at class level > 10:**
```python
Rule(
    id="class-level-magic-number",
    severity=Severity.ERROR,
    matchers=[AstNodeMatcher(node_type="literal_expression", scope="class")],
    file_globs=["**/*.ts"],
    workspace="frontend/",
    predicates=[IntPredicate(op=">", value=10)],
    message="Magic number {matched_value} at class level. Move to constants file (**/constants.ts).",
)
```

**Constants only in constants.ts (AND):**
```python
Rule(
    id="constants-file-location",
    severity=Severity.ERROR,
    matchers=[
        RegexMatcher(r"\bconst\b"),               # has const keyword
        PathNotMatchingMatcher("**/constants.ts"), # and not in constants file
    ],
    file_globs=["**/*.ts"],
    workspace="frontend/",
    message="Constants must only be defined in files matching **/constants.ts",
)
```
Note: flat matcher list = implicit `AllOf` (AND). All must produce ≥1 match.

**Raw hex OR rgba (OR combinator):**
```python
Rule(
    id="no-raw-color",
    severity=Severity.ERROR,
    matchers=[AnyOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        RegexMatcher(r"\brgba?\("),
    ])],
    file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
    exclude_globs=["**/*.spec.ts"],
    workspace="frontend/",
    message="Raw color '{matched_value}' found. Use var(--color-*) from colors.scss.",
)
```

**File must contain a license header (Not combinator):**
```python
Rule(
    id="must-have-license",
    severity=Severity.ERROR,
    matchers=[Not(
        RegexMatcher(r"Copyright|Licensed|SPDX-License"),
        message_on_absence="No license header found.",
    )],
    file_globs=["**/*.ts", "**/*.py"],
    exclude_globs=["**/__init__.py", "**/*.spec.ts"],
    workspace=".",
    message="File is missing a license header.",
)
```

**Exactly one of: either .css file OR .scss file (XOR):**
```python
Rule(
    id="single-stylesheet-format",
    severity=Severity.WARN,
    matchers=[OneOf([
        PathNotMatchingMatcher("**/*.css"),
        PathNotMatchingMatcher("**/*.scss"),
    ])],
    file_globs=["**/*"],
    workspace="frontend/",
    message="Directory should use either CSS or SCSS, not both.",
)
```

**Max lines:**
```python
Rule(
    id="max-lines-readme",
    severity=Severity.WARN,
    matchers=[LineCountMatcher(max_lines=200)],
    file_globs=["README.md"],
    message="README.md has {matched_value} lines (max 200).",
)
```

**LLM consequence on verbose README:**
```python
Rule(
    id="verbose-readme",
    severity=Severity.WARN,
    matchers=[LineCountMatcher(max_lines=200)],
    file_globs=["README.md"],
    message="README.md is {matched_value} lines. LLM will analyze verbosity.",
    llm_consequence=LLMConsequence(
        provider="skainet",
        model="tngtech/DeepSeek-TNG-R1T2-Chimera",
        prompt="The following file has been flagged as too long. Report what in the file is too verbose and where (line numbers). Be specific.",
    ),
)
```

**Only defined CSS variables (cross-file allowlist):**
```python
import re
Rule(
    id="only-defined-css-vars",
    severity=Severity.ERROR,
    matchers=[AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )],
    file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
    workspace="frontend/",
    read_targets=["**/colors.scss"],
    message="Undefined CSS variable: --{matched_value}. Defined variables are in colors.scss.",
)
```

**Max 3 comment lines per function:**
```python
Rule(
    id="max-comments-per-function",
    severity=Severity.WARN,
    matchers=[CommentPerFunctionMatcher(max_comments=3)],
    file_globs=["**/*.ts", "**/*.py"],
    workspace=".",
    message="Function has {matched_value} comment lines (max 3).",
)
```

**Nested combinators: (regex A OR regex B) AND NOT in test files:**
```python
Rule(
    id="no-console-log-or-debugger",
    severity=Severity.ERROR,
    matchers=[AllOf([
        AnyOf([
            RegexMatcher(r"\bconsole\.log\b"),
            RegexMatcher(r"\bdebugger\b"),
        ]),
        PathNotMatchingMatcher("**/*.spec.ts"),
    ])],
    file_globs=["**/*.ts"],
    workspace="frontend/",
    message="'{matched_value}' found in production code.",
)
```

### 3.9 Custom Rule subclass (escape hatch)

For logic the DSL can't express, subclass `Rule` and override `check()`:

```python
class ComplexRule(Rule):
    id = "complex-rule"
    severity = Severity.ERROR
    file_globs = ["**/*.ts"]

    def check(self, file_ctx, shared_ctx):
        # Full access to file_ctx, shared_ctx
        # Return list[Match]
        ...
```

### 3.10 Matcher/predicate registry

Matchers and predicates are auto-discovered from `enforcer.matchers` and
`enforcer.predicates` packages. Custom matchers can be registered:

```python
from enforcer import register_matcher

@register_matcher
class MyCustomMatcher:
    ...
```

### 3.11 Needs inference

The tool infers `Needs` from matchers:
- `RegexMatcher`, `LineCountMatcher`, `CharCountMatcher` → `Needs.RAW`
- `AstNodeMatcher` with `.ts` files → `Needs.AST_TS`
- `AstNodeMatcher` with `.py` files → `Needs.AST_PY`
- `PathNotMatchingMatcher` → `Needs.PATH` (no content read)
- `AllowlistMatcher` → `Needs.RAW` + read_targets

A rule's `needs` = union of all matchers' needs. The tool uses this for
parse-once optimization (section 4).

---

## 4. Parse-Once Optimization

### Problem

Multiple rules target the same file. Naive approach: each rule reads + parses
the file independently → N rules × N parse passes.

### Solution

1. **Rule registry**: tool collects all rules, groups by `file_globs`.
2. **Need aggregation**: for each file, tool unions all `needs` across matching
   rules. Example: file `x.ts` matches 3 rules — rule A needs `RAW`, rule B
   needs `AST_TS`, rule C needs `RAW`. Union: `{RAW, AST_TS}`.
3. **Single parse pass**: tool reads file once, produces raw text. If any rule
   needs an AST, parses once via tree-sitter (language inferred from file
   extension). Builds a `FileContext` with all needed data.
4. **Read-target parsing**: read targets are parsed once (same optimization
   applies — if two rules both read `colors.scss`, it's parsed once).

```python
@dataclass
class FileContext:
    path: str
    raw: str | None = None        # present if any rule needs Needs.RAW
    ast: tree_sitter.Tree | None = None  # present if any rule needs Needs.AST_*
    # AST present only if at least one rule declared the corresponding need
```

### Language detection

File extension → tree-sitter language:

| Extension | Language | AST need |
|-----------|----------|----------|
| `.ts`, `.tsx`, `.js`, `.jsx` | TypeScript / JavaScript | `AST_TS` |
| `.py` | Python | `AST_PY` |
| `.scss`, `.css` | SCSS / CSS | `AST_CSS` |
| other | (no AST, RAW only) | — |

---

## 5. LLM Execution

### When LLM fires

1. Deterministic rule runs → produces matches.
2. If match's rule has `llm_consequence` configured → LLM call scheduled.
3. LLM receives: file content (from `file_ctx.raw`) + the `prompt` from the
   consequence config.
4. LLM response attached to match as `llm_response` field.

### Execution model

- **Parallel** with concurrency cap (default 5).
- Only fires when a deterministic rule **fails** (produces matches).
- LLM calls are the exception, not the norm.
- Provider config from `opencode.json` — OpenAI-compatible API.

### Provider configuration

LLM consequences reference a provider + model from the project's
`opencode.json` (or a standalone config). The tool reads provider baseURL +
headers + model name and makes a standard OpenAI-compatible chat completion
call.

```python
llm_consequence = LLMConsequence(
    provider="skainet",
    model="tngtech/DeepSeek-TNG-R1T2-Chimera",
    prompt="...",
    # Optional: override baseURL, headers from opencode.json
)
```

### API call

```
POST {provider.baseURL}/chat/completions
Headers: {provider.headers}
Body: {
  "model": "{model}",
  "messages": [
    {"role": "user", "content": "{prompt}\n\n--- FILE CONTENT ---\n{file_raw}"}
  ]
}
```

Response text → `match.llm_response`.

---

## 6. Output Format

### JSON (`--format json`, default for pre-commit hook)

```json
{
  "summary": {
    "total": 3,
    "errors": 2,
    "warnings": 1,
    "info": 0
  },
    "issues": [
    {
      "file": "src/app/components/artifact-kind-header.component.ts",
      "line": 144,
      "column": 21,
      "rule_id": "no-raw-hex",
      "severity": "error",
      "message": "Raw hex color '#c8e6c9' found. Use var(--color-*) from colors.scss.",
      "fix_instruction": "Replace with the appropriate var(--color-*) from colors.scss."
    },
    {
      "file": "src/app/components/artifact-kind-header.component.ts",
      "line": 145,
      "column": 15,
      "rule_id": "no-raw-hex",
      "severity": "error",
      "message": "Raw hex color '#1b5e20' found. Use var(--color-*) from colors.scss.",
      "fix_instruction": "Replace with the appropriate var(--color-*) from colors.scss."
    },
    {
      "file": "README.md",
      "line": 0,
      "column": 0,
      "rule_id": "verbose-readme",
      "severity": "warn",
      "message": "README.md is 247 lines (max 200). LLM analysis: ...",
      "llm_response": "Lines 45-80 contain detailed architecture diagrams that belong in docs/architecture.md. Lines 120-140 describe internal data flow..."
    }
  ]
}
```

### Text (`--format text`, default for humans)

```
src/app/components/artifact-kind-header.component.ts:144:21 [ERROR] no-raw-hex
  Raw hex color '#c8e6c9' found. Use var(--color-*) from colors.scss.
  Fix: Replace with the appropriate var(--color-*) from colors.scss.

src/app/components/artifact-kind-header.component.ts:145:15 [ERROR] no-raw-hex
  Raw hex color '#1b5e20' found. Use var(--color-*) from colors.scss.
  Fix: Replace with the appropriate var(--color-*) from colors.scss.

README.md [WARN] verbose-readme
  README.md is 247 lines (max 200).
  LLM: Lines 45-80 contain detailed architecture diagrams that belong in
  docs/architecture.md. Lines 120-140 describe internal data flow...

Summary: 3 issues (2 errors, 1 warning). Commit blocked.
```

### Exit code

- `0` — no error-severity issues (warnings/info allowed)
- `1` — one or more error-severity issues

---

## 7. Configuration

### `enforcer_config.py` (config-as-code)

Rules are composed declaratively from matchers + predicates. No rule classes
needed — the DSL handles 90% of cases inline. Custom Rule subclasses only for
complex logic (section 3.7).

```python
import re
from enforcer import (
    Rule, Severity, LLMConsequence,
    RegexMatcher, AstNodeMatcher, LineCountMatcher, CharCountMatcher,
    PathNotMatchingMatcher, CommentPerFunctionMatcher, AllowlistMatcher,
    IntPredicate, StringLengthPredicate, StringMatchesPredicate,
)

# Global workspace — default base path for rules that don't override
# Can also be set via --workspace CLI flag (CLI flag takes precedence)
WORKSPACE = "."

# Rule registry — explicit registration, composed from DSL building blocks
RULES = [
    # ── CSS / design tokens — scoped to frontend/ ──────────────
    Rule(
        id="no-raw-hex",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
        file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
        workspace="frontend/",
        read_targets=["**/colors.scss"],
        message="Raw hex color '{matched_value}' found. Use var(--color-*) from colors.scss.",
        fix_instruction="Replace with the appropriate var(--color-*) from colors.scss.",
    ),
    Rule(
        id="only-defined-css-vars",
        severity=Severity.ERROR,
        matchers=[AllowlistMatcher(
            extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
            consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
            read_target="**/colors.scss",
        )],
        file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
        workspace="frontend/",
        read_targets=["**/colors.scss"],
        message="Undefined CSS variable: --{matched_value}. Defined variables are in colors.scss.",
    ),

    # ── TypeScript conventions — scoped to frontend/ ───────────
    Rule(
        id="constants-file-location",
        severity=Severity.ERROR,
        matchers=[
            RegexMatcher(r"\bconst\b"),
            PathNotMatchingMatcher("**/constants.ts"),
        ],
        file_globs=["**/*.ts"],
        workspace="frontend/",
        message="Constants must only be defined in files matching **/constants.ts",
    ),
    Rule(
        id="class-level-magic-number",
        severity=Severity.ERROR,
        matchers=[AstNodeMatcher(node_type="literal_expression", scope="class")],
        file_globs=["**/*.ts"],
        workspace="frontend/",
        predicates=[IntPredicate(op=">", value=10)],
        message="Magic number {matched_value} at class level. Move to constants file (**/constants.ts).",
    ),

    # ── Documentation — repo root ──────────────────────────────
    Rule(
        id="max-lines-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=200)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 200).",
    ),
    Rule(
        id="verbose-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=200)],
        file_globs=["README.md"],
        message="README.md is {matched_value} lines. LLM will analyze verbosity.",
        llm_consequence=LLMConsequence(
            provider="skainet",
            model="tngtech/DeepSeek-TNG-R1T2-Chimera",
            prompt="The following file has been flagged as too long. Report what in the file is too verbose and where (line numbers). Be specific.",
        ),
    ),
]

# Severity → action mapping (configurable)
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",   # non-zero exit, commit blocked
    Severity.WARN: "print",    # printed, commit allowed
    Severity.INFO: "hint",     # printed, commit allowed
}

# LLM execution config
LLM_CONFIG = {
    "concurrency": 5,
    "timeout": 30,
    # Provider resolved from opencode.json in project root or ~/.config/opencode/
}
```

### Pre-commit hook registration (`.pre-commit-config.yaml`)

```yaml
- repo: local
  hooks:
    - id: enforcer
      name: convention enforcer
      language: system
      entry: enforcer check --staged --format json
      pass_filenames: false
```

---

## 8. CLI

```
enforcer check [options]

Options:
  --staged              Check staged files only (default)
  --all                 Check entire repo
  --paths FILE...       Check specific files
  --format json|text    Output format (default: text)
  --config PATH         Config file (default: enforcer_config.py)
  --workspace PATH      Global workspace root (default: . or WORKSPACE from config).
                        Base path for file_globs and read_targets resolution.
                        Overridden by per-rule workspace if set.
  --severity error|warn|info  Minimum severity to report (default: info)
  --no-llm              Skip LLM consequences (deterministic only)
```

---

## 9. MCP Server

```
enforcer mcp
```

Exposes a single tool:

**Tool: `check_conventions`**
- **Input**: `{ "paths": ["file1.ts", "file2.py"], "format": "json" }`
  - If `paths` omitted, checks staged files.
- **Output**: JSON (same format as CLI `--format json`).

Agent calls this before committing to self-check. If issues found, agent reads
the JSON, reads fix instructions, fixes, re-checks.

---

## 10. Package Structure

```
enforcer/
├── __init__.py            # public API: Rule, Severity, Match, etc.
├── cli.py                 # CLI entry point (click/argparse)
├── config.py              # config loader (reads enforcer_config.py)
├── context.py             # FileContext builder (parse-once logic)
├── runner.py              # Rule Runner (executes rules, collects matches)
├── reporter.py            # JSON / text output formatter
├── llm.py                 # LLM Executor (parallel, OpenAI-compatible)
├── mcp_server.py          # MCP server (check_conventions tool)
├── matchers/
│   ├── __init__.py        # auto-discover all matchers
│   ├── regex.py           # RegexMatcher
│   ├── ast_node.py        # AstNodeMatcher
│   ├── line_count.py      # LineCountMatcher
│   ├── char_count.py      # CharCountMatcher
│   ├── path_pattern.py    # PathNotMatchingMatcher
│   ├── comment_density.py # CommentPerFunctionMatcher
│   └── allowlist.py       # AllowlistMatcher
├── predicates/
│   ├── __init__.py        # auto-discover all predicates
│   ├── int_compare.py     # IntPredicate
│   ├── string_length.py   # StringLengthPredicate
│   └── string_matches.py  # StringMatchesPredicate
└── parsers/
    ├── __init__.py
    ├── tree_sitter.py     # tree-sitter wrapper (TS, Python, CSS/SCSS)
    └── language.py        # file extension → language detection
```

Rules themselves live in the project's `enforcer_config.py`, composed from the
DSL building blocks above. Custom matchers/predicates can be registered via
`@register_matcher` / `@register_predicate` from a project-local package.

---

## 11. Data Flow

```
1. CLI invoked (pre-commit hook or manual)
   │
2. Config Loader reads enforcer_config.py
   │  → instantiates rules, resolves WORKSPACE global
   │  → CLI --workspace flag overrides config WORKSPACE
   │
3. File Resolver determines target files
   │  → --staged: git diff --cached --name-only
   │  → --all: walk repo (respect .gitignore)
   │  → --paths: explicit list
   │  → files filtered by each rule's workspace + file_globs
   │    (rule.workspace if set, else global workspace)
   │
4. Read-target files resolved + parsed (once each)
   │  → resolved relative to rule's workspace
   │  → stored in shared context dict (keyed by basename)
   │
5. For each target file:
   │  → match against rule file_globs (relative to rule workspace)
   │  → aggregate needs across matching rules
   │  → read file once, parse once (raw + AST if needed)
   │  → build FileContext
   │
6. Rule Runner executes all matching rules against FileContext
   │  → collects ALL matches (not just first)
   │  → deterministic rules run first
   │
7. For matches with llm_consequence:
   │  → LLM Executor fires (parallel, capped at 5)
   │  → LLM response attached to match
   │
8. Reporter formats output (JSON or text)
   │  → prints to stdout
   │  → exit code: 0 if no errors, 1 if any errors
   │
9. Done
```

---

## 12. Testing Strategy

Tests use `pytest`. Fixtures under `tests/fixtures/`. Every component tested
in isolation (unit) + together (integration). LLM rules tested with mock
provider — no real API calls in CI.

### 12.1 Test structure

```
tests/
├── conftest.py                 # shared fixtures: sample files, FileContext builder
├── fixtures/
│   ├── sample.ts               # TS file with hex colors, magic numbers, console.log
│   ├── sample_clean.ts         # TS file with no violations
│   ├── sample.scss             # SCSS with raw hex, undefined vars
│   ├── colors.scss             # CSS variables definition file
│   ├── README.md               # verbose README (>200 lines)
│   ├── README_short.md         # clean README
│   ├── sample.py               # Python with magic numbers
│   └── constants.ts            # constants file
├── test_matchers/
│   ├── test_regex_matcher.py
│   ├── test_ast_node_matcher.py
│   ├── test_line_count_matcher.py
│   ├── test_char_count_matcher.py
│   ├── test_path_pattern_matcher.py
│   ├── test_comment_density_matcher.py
│   └── test_allowlist_matcher.py
├── test_predicates/
│   ├── test_int_predicate.py
│   ├── test_string_length_predicate.py
│   ├── test_string_matches_predicate.py
│   └── test_predicate_combinators.py
├── test_combinators/
│   ├── test_all_of.py
│   ├── test_any_of.py
│   ├── test_one_of.py
│   ├── test_not.py
│   ├── test_none_of.py
│   └── test_nested_combinators.py
├── test_rule.py                # Rule.check, message rendering, exclude_globs
├── test_config.py              # config loading, workspace resolution
├── test_context.py             # FileContext builder, parse-once optimization
├── test_runner.py              # Rule Runner, all-match collection
├── test_reporter.py            # JSON output, text output, exit codes
├── test_llm.py                 # LLM Executor with mock provider
├── test_cli.py                 # CLI arg parsing, --staged/--all/--paths
├── test_mcp.py                 # MCP server, check_conventions tool
├── test_parse_once.py          # verify each file parsed exactly once
├── test_exclude_globs.py       # glob exception behavior
└── test_integration.py         # full end-to-end on fixture repo
```

### 12.2 Matcher tests

Each matcher tested with: positive case (finds matches), negative case (no
matches), edge cases (empty file, binary file, huge file).

```python
# test_matchers/test_regex_matcher.py
import pytest
from enforcer import RegexMatcher, FileContext

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
```

```python
# test_matchers/test_line_count_matcher.py
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
```

```python
# test_matchers/test_allowlist_matcher.py
def test_allowlist_finds_undefined():
    import re
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
```

### 12.3 Combinator tests

```python
# test_combinators/test_all_of.py
def test_all_of_all_match():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2  # both matchers' results

def test_all_of_one_missing():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert matches == []  # regex B found nothing → AllOf fails

def test_all_of_empty():
    ctx = FileContext(path="x.ts", raw="")
    m = AllOf([RegexMatcher(r"test")])
    assert m.find(ctx) == []

# test_combinators/test_any_of.py
def test_any_of_one_matches():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = AnyOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),  # no match
        RegexMatcher(r"\bconst\b"),            # match
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
    assert len(matches) == 2  # both contributed

def test_any_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AnyOf([
        RegexMatcher(r"#fff"),
        RegexMatcher(r"\bconst\b"),
    ])
    assert m.find(ctx) == []

# test_combinators/test_one_of.py
def test_one_of_exactly_one():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = OneOf([
        RegexMatcher(r"#fff"),    # no match
        RegexMatcher(r"\bconst\b"),  # match
    ])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_one_of_two_matchers_match():
    ctx = FileContext(path="x.ts", raw="const #fff;")
    m = OneOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    assert m.find(ctx) == []  # 2 matchers matched → XOR fails

def test_one_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = OneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bconst\b")])
    assert m.find(ctx) == []

# test_combinators/test_not.py
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

# test_combinators/test_none_of.py
def test_none_of_all_absent():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_none_of_one_present():
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    assert m.find(ctx) == []

# test_combinators/test_nested_combinators.py
def test_nested_anyof_inside_allof():
    ctx = FileContext(path="x.ts", raw="console.log('x'); #fff;")
    m = AllOf([
        AnyOf([RegexMatcher(r"\bconsole\.log\b"), RegexMatcher(r"\bdebugger\b")]),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2  # console.log + #fff

def test_nested_not_inside_allof():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        Not(RegexMatcher(r"\bdebugger\b")),
    ])
    matches = m.find(ctx)
    # #fff found + debugger absent → both conditions met
    # Not returns 1 match (absent), regex returns 1 match (#fff)
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
    # Inner: Not(debugger) → 1 match (absent), console.log → 1 match → AnyOf = 2
    # Inner: NoneOf(#fff) → #fff present → returns [] → Not([]) → 1 match (absent)
    # AllOf: [2, 1] → both non-empty → total 3
    matches = m.find(ctx)
    assert len(matches) == 3
```

### 12.4 Predicate tests

```python
# test_predicates/test_int_predicate.py
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

# test_predicates/test_string_length_predicate.py
def test_string_length():
    m = Match(file="x", line=1, matched_value="hello")
    assert StringLengthPredicate(op=">", value=3).test(m)
    assert StringLengthPredicate(op=">", value=5).test(m) is False
    assert StringLengthPredicate(op="==", value=5).test(m)

def test_string_length_empty():
    m = Match(file="x", line=1, matched_value="")
    assert StringLengthPredicate(op="==", value=0).test(m)

# test_predicates/test_string_matches_predicate.py
def test_string_matches():
    m = Match(file="x", line=1, matched_value="#aabbcc")
    assert StringMatchesPredicate(r"^#").test(m)
    assert StringMatchesPredicate(r"^#ff").test(m) is False

def test_string_not_matches():
    m = Match(file="x", line=1, matched_value="var(--color)")
    assert StringNotMatchesPredicate(r"^#").test(m)
    assert StringNotMatchesPredicate(r"^var").test(m) is False

# test_predicates/test_predicate_combinators.py
def test_all_predicates():
    m = Match(file="x", line=1, matched_value="42")
    p = All([IntPredicate(op=">", value=10), IntPredicate(op="<", value=100)])
    assert p.test(m)

def test_any_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = Any([IntPredicate(op=">", value=50), IntPredicate(op="<", value=50)])
    assert p.test(m)

def test_not_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = NotP(IntPredicate(op=">", value=50))
    assert p.test(m)
```

### 12.5 Rule tests

```python
# test_rule.py
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
    # Both match → reports both
    ctx = FileContext(path="x.ts", raw="const #fff;")
    matches = rule.check(ctx, {})
    assert len(matches) == 2

    # One missing → reports nothing
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
    assert len(matches) == 5  # ALL matches, not just first
```

### 12.6 Parse-once tests

```python
# test_parse_once.py
def test_file_read_once(mocker):
    """Multiple rules targeting same file → file read exactly once."""
    mock_open = mocker.patch("builtins.open", mocker.mock_open(read_data="const #fff;"))
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")], file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")], file_globs=["**/*.ts"], message="x"),
        Rule(id="c", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")], file_globs=["**/*.ts"], message="x"),
    ]
    runner = Runner(rules, workspace=".")
    runner.run(paths=["x.ts"])
    assert mock_open.call_count == 1  # read once, shared across 3 rules

def test_ast_parsed_once(mocker):
    """Multiple AST rules → tree-sitter parse called once."""
    mock_parse = mocker.patch("enforcer.parsers.tree_sitter.parse")
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[AstNodeMatcher(node_type="literal_expression")], file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[AstNodeMatcher(node_type="identifier")], file_globs=["**/*.ts"], message="x"),
    ]
    runner = Runner(rules, workspace=".")
    runner.run(paths=["x.ts"])
    assert mock_parse.call_count == 1

def test_read_target_parsed_once(mocker):
    """Multiple rules with same read_target → target parsed once."""
    mock_open = mocker.patch("builtins.open", mocker.mock_open(read_data="--color-primary: #fff;"))
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[AllowlistMatcher(...)], read_targets=["**/colors.scss"], ...),
        Rule(id="b", severity=Severity.ERROR, matchers=[AllowlistMatcher(...)], read_targets=["**/colors.scss"], ...),
    ]
    runner = Runner(rules, workspace=".")
    runner.run(paths=["x.ts"])
    # x.ts read once + colors.scss read once = 2 total, not 3
    assert mock_open.call_count == 2
```

### 12.7 Reporter tests

```python
# test_reporter.py
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

def test_empty_output():
    output = Reporter(format="json").render([])
    data = json.loads(output)
    assert data["summary"]["total"] == 0
    assert data["issues"] == []

def test_text_empty_output():
    output = Reporter(format="text").render([])
    assert "No issues found" in output or output.strip() == ""

def test_multiple_severities_sorted():
    matches = [
        Match(file="a.ts", line=1, message="info", severity=Severity.INFO),
        Match(file="b.ts", line=1, message="error", severity=Severity.ERROR),
        Match(file="c.ts", line=1, message="warn", severity=Severity.WARN),
    ]
    output = Reporter(format="text").render(matches)
    # Errors first, then warnings, then info
    error_pos = output.index("ERROR")
    warn_pos = output.index("WARN")
    info_pos = output.index("INFO")
    assert error_pos < warn_pos < info_pos
```

### 12.8 LLM tests (mock provider)

```python
# test_llm.py
def test_llm_fires_on_rule_failure(mocker):
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Lines 45-80 too verbose"}}]}
    mock_post = mocker.patch("httpx.post", return_value=mock_response)

    rule = Rule(
        id="verbose-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=2)],
        file_globs=["README.md"],
        message="Too long",
        llm_consequence=LLMConsequence(
            provider="skainet",
            model="test-model",
            prompt="Analyze verbosity.",
        ),
    )
    ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
    matches = rule.check(ctx, {})

    mock_post.assert_called_once()
    assert matches[0].llm_response == "Lines 45-80 too verbose"

def test_llm_skipped_when_rule_passes(mocker):
    mock_post = mocker.patch("httpx.post")
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
    mock_post.assert_not_called()
    assert matches == []

def test_llm_no_llm_flag(mocker):
    mock_post = mocker.patch("httpx.post")
    rule = Rule(
        id="verbose-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=2)],
        file_globs=["README.md"],
        message="Too long",
        llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x"),
    )
    runner = Runner(rules=[rule], no_llm=True)
    ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
    matches = runner.run_file(ctx, {})
    mock_post.assert_not_called()
    assert len(matches) == 1  # deterministic match still reported
    assert matches[0].llm_response == ""  # no LLM response

def test_llm_parallel_execution(mocker):
    """Multiple LLM rules fire in parallel."""
    call_count = 0
    def mock_post_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = mocker.Mock()
        resp.json.return_value = {"choices": [{"message": {"content": f"response {call_count}"}}]}
        return resp

    mocker.patch("httpx.post", side_effect=mock_post_side_effect)
    rules = [
        Rule(id=f"rule-{i}", severity=Severity.WARN,
             matchers=[LineCountMatcher(max_lines=2)],
             file_globs=[f"file{i}.md"], message="x",
             llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x"))
        for i in range(5)
    ]
    runner = Runner(rules, llm_concurrency=5)
    for i in range(5):
        ctx = FileContext(path=f"file{i}.md", raw="line1\nline2\nline3\n")
        runner.run_file(ctx, {})
    runner.flush_llm()  # wait for all parallel calls
    assert call_count == 5

def test_llm_timeout(mocker):
    mocker.patch("httpx.post", side_effect=httpx.TimeoutException("timeout"))
    rule = Rule(
        id="test", severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=2)],
        file_globs=["README.md"], message="x",
        llm_consequence=LLMConsequence(provider="skainet", model="test", prompt="x", timeout=1),
    )
    ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
    matches = rule.check(ctx, {})
    assert matches[0].llm_response == ""  # graceful fallback on timeout
```

### 12.9 CLI tests

```python
# test_cli.py
def test_cli_staged(mocker):
    mocker.patch("subprocess.check_output", return_value=b"x.ts\ny.ts\n")
    runner = mocker.patch("enforcer.runner.Runner.run")
    runner.return_value = []
    result = CliRunner().invoke(cli, ["check", "--staged", "--format", "json"])
    assert result.exit_code == 0

def test_cli_all(mocker):
    os_walk = mocker.patch("os.walk", return_value=[(".", [], ["x.ts", "y.ts"])])
    mocker.patch("enforcer.runner.Runner.run", return_value=[])
    result = CliRunner().invoke(cli, ["check", "--all"])
    assert result.exit_code == 0

def test_cli_paths():
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts", "y.ts"])
    assert result.exit_code == 0

def test_cli_workspace(mocker):
    runner = mocker.patch("enforcer.runner.Runner")
    runner.return_value.run.return_value = []
    result = CliRunner().invoke(cli, ["check", "--workspace", "frontend/", "--paths", "x.ts"])
    assert result.exit_code == 0
    # verify workspace was passed through

def test_cli_format_json(mocker):
    mocker.patch("enforcer.runner.Runner.run", return_value=[])
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts", "--format", "json"])
    data = json.loads(result.output)
    assert "summary" in data
    assert "issues" in data

def test_cli_format_text(mocker):
    mocker.patch("enforcer.runner.Runner.run", return_value=[])
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts", "--format", "text"])
    assert result.exit_code == 0

def test_cli_no_llm(mocker):
    runner = mocker.patch("enforcer.runner.Runner")
    runner.return_value.run.return_value = []
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts", "--no-llm"])
    assert result.exit_code == 0

def test_cli_exit_code_on_error(mocker):
    match = Match(file="x.ts", line=1, message="err", severity=Severity.ERROR)
    mocker.patch("enforcer.runner.Runner.run", return_value=[match])
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts"])
    assert result.exit_code == 1

def test_cli_exit_code_on_warn_only(mocker):
    match = Match(file="x.ts", line=1, message="warn", severity=Severity.WARN)
    mocker.patch("enforcer.runner.Runner.run", return_value=[match])
    result = CliRunner().invoke(cli, ["check", "--paths", "x.ts"])
    assert result.exit_code == 0

def test_cli_config_path(mocker):
    mocker.patch("enforcer.runner.Runner.run", return_value=[])
    result = CliRunner().invoke(cli, ["check", "--config", "custom_config.py", "--paths", "x.ts"])
    assert result.exit_code == 0
```

### 12.10 Integration test

```python
# test_integration.py
def test_full_run_on_fixture_repo(tmp_path):
    """End-to-end: create fixture repo with known violations, run enforcer, check output."""
    # Create fixture files
    (tmp_path / "colors.scss").write_text("--color-primary: #fff;\n--color-secondary: #000;\n")
    (tmp_path / "component.ts").write_text(
        "background: #c8e6c9;\n"  # raw hex violation
        "color: var(--color-primary);\n"
        "border: var(--color-undefined);\n"  # undefined var
    )
    (tmp_path / "component.spec.ts").write_text("background: #fff;\n")  # excluded
    (tmp_path / "README.md").write_text("\n".join(["line"] * 250))  # too long

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

    runner = Runner(rules, workspace=str(tmp_path), no_llm=True)
    all_matches = runner.run_all()

    # component.ts: 1 raw hex violation
    hex_matches = [m for m in all_matches if m.rule_id == "no-raw-hex"]
    assert len(hex_matches) == 1
    assert hex_matches[0].matched_value == "#c8e6c9"

    # component.ts: 1 undefined var
    var_matches = [m for m in all_matches if m.rule_id == "only-defined-css-vars"]
    assert len(var_matches) == 1
    assert var_matches[0].matched_value == "color-undefined"

    # component.spec.ts: excluded, no matches
    spec_matches = [m for m in all_matches if ".spec." in m.file]
    assert spec_matches == []

    # README.md: 1 line count violation
    readme_matches = [m for m in all_matches if m.rule_id == "max-lines"]
    assert len(readme_matches) == 1

    # Exit code
    assert Reporter().exit_code(all_matches) == 1  # has errors

def test_full_run_clean_repo(tmp_path):
    """No violations → empty output, exit 0."""
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
    runner = Runner(rules, workspace=str(tmp_path), no_llm=True)
    matches = runner.run_all()
    assert matches == []
    assert Reporter().exit_code(matches) == 0
```

### 12.11 Test commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=enforcer --cov-report=term-missing

# Run only matcher tests
pytest tests/test_matchers/

# Run only combinator tests
pytest tests/test_combinators/

# Run integration tests
pytest tests/test_integration.py

# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_combinators/test_all_of.py::test_all_of_all_match
```

---

## 13. Dependencies

| Dependency | Purpose |
|-----------|---------|
| `tree-sitter` | Unified AST parsing for TS/Python/CSS/SCSS |
| `tree-sitter-typescript` | TS/JS grammar |
| `tree-sitter-python` | Python grammar |
| `tree-sitter-css` | CSS/SCSS grammar |
| `httpx` | LLM API calls (async, OpenAI-compatible) |
| `click` (or `argparse`) | CLI argument parsing |
| `mcp` | MCP server framework (if available; else stdio JSON-RPC) |
| `pytest` | Testing framework |
| `pytest-mock` | mocker fixture for mocking |
| `pytest-cov` | Coverage reporting |

---

## 14. Open Questions

1. **tree-sitter language for SCSS**: `tree-sitter-css` handles CSS but SCSS
   has nesting, variables, mixins. May need `tree-sitter-scss` or fall back
   to regex for SCSS-specific constructs. → Investigate during implementation.

2. **MCP server protocol**: Use the `mcp` Python SDK if available, or implement
   a minimal stdio JSON-RPC server. → Check what's available at implementation
   time.

3. **Rule ordering**: Should rules run in a specific order (e.g. read-target
   rules before consuming rules)? Currently: read targets parsed first, then
   rules run against files. Order between rules doesn't matter (each is
   independent). → Confirm this holds.
