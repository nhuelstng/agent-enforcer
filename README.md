# pre-commit-agent-enforcer

Deterministic convention enforcement for coding agents — a composable DSL, CLI, and MCP server that blocks commits violating your project conventions.

## Installation

Editable install (development):

```bash
pip install -e .
```

Or install from the repo:

```bash
pip install .
```

Optional extras:

```bash
pip install -e ".[dev]"   # pytest, pytest-mock, pytest-cov
pip install -e ".[mcp]"   # mcp sdk
```

## Quickstart

1. Create an `enforcer_config.py` at your repo root declaring your rules (see [enforcer_config.py](enforcer_config.py) for a full example).

2. Run a check on staged files:

```bash
enforcer check --staged
```

3. Install the git hook so checks run automatically on `git commit`:

```bash
enforcer install
```

## CLI

All commands are exposed under the `enforcer` entry point.

### `enforcer check`

Check files for convention violations.

| Flag | Description |
|------|-------------|
| `--staged` | Check only files staged in git (`git diff --cached`). |
| `--all` | Walk the entire repo (skips `.git`, `node_modules`, `__pycache__`, `.venv`, etc.). |
| `--paths PATH...` | Check specific files. Repeatable. |
| `--format json\|text\|sarif` | Output format (default: `text`). |
| `--config PATH` | Path to config module (default: `enforcer_config.py`). |
| `--workspace PATH` | Global workspace root (overrides config). |
| `--severity error\|warn\|info` | Minimum severity to report (default: `info`). |
| `--no-llm` | Skip LLM consequences. |
| `--rule-id ID` | Run only this rule ID. |
| `--confirm-read-warnings` | Acknowledge WARN-severity findings and allow the commit to proceed. |

Examples:

```bash
enforcer check --staged
enforcer check --all --format sarif
enforcer check --paths src/foo.ts src/bar.ts --rule-id no-raw-hex
enforcer check --staged --confirm-read-warnings
```

### `enforcer docs`

Generate markdown documentation of all configured rules.

| Flag | Description |
|------|-------------|
| `--output FILE` (`-o`) | Write to file instead of stdout. |

```bash
enforcer docs -o CONVENTIONS.md
```

### `enforcer install`

Install the pre-commit hook into `.git/hooks/pre-commit`.

| Flag | Description |
|------|-------------|
| `--force` | Overwrite an existing hook. |

```bash
enforcer install
enforcer install --force
```

## Configuration

All configuration lives in `enforcer_config.py`. The module exposes top-level
symbols that the tool loads at runtime.

### `RULES`

A list of `Rule` dataclass instances.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique rule identifier (used by `--rule-id`, `verify_fix`). |
| `severity` | `Severity` | One of `Severity.ERROR`, `Severity.WARN`, `Severity.INFO`. |
| `matchers` | `list` | Matcher instances (or a single combinator wrapping them). ANDed together. |
| `file_globs` | `list[str]` | Glob patterns selecting which files the rule applies to. |
| `exclude_globs` | `list[str]` | Glob patterns to exclude (default `[]`). |
| `read_targets` | `list[str]` | Extra files whose contents are made available to matchers via `shared_ctx` (default `[]`). |
| `message` | `str \| Callable` | Message template. Supports placeholders `{file}`, `{line}`, `{column}`, `{matched_value}`. Can also be a callable `(Match) -> str`. |
| `fix_instruction` | `str` | Human/agent-readable fix hint (default `""`). |
| `llm_consequence` | `LLMConsequence \| None` | Optional LLM review config (default `None`). |
| `workspace` | `str \| None` | Per-rule workspace root override (default `None`). |
| `predicates` | `list` | Predicate filters applied to matches (default `[]`). |
| `diff_only` | `bool` | If `True`, only flag matches on lines changed in the current staged diff (default `False`). Requires `--staged`. |

### `SEVERITY_ACTIONS`

Mapping from `Severity` to the action the reporter/hook takes:

| Action | Behavior |
|--------|----------|
| `block` | Non-zero exit code; commit is blocked. |
| `block_warn` | Blocks unless `--confirm-read-warnings` (or `ENFORCER_CONFIRM_WARNINGS=1`) is set. |
| `print` | Print finding, do not block. |
| `hint` | Print as a hint, do not block. |

### `LLM_CONFIG`

Dict tuning LLM consequence execution:

```python
LLM_CONFIG = {
    "concurrency": 5,
    "timeout": 30,
}
```

### `WORKSPACE`

String. Global workspace root (default `"."`).

## Diff-awareness

Rules can be scoped to changed lines only, preventing re-flagging of pre-existing technical debt:

```python
Rule(
    id="no-print",
    severity=Severity.ERROR,
    matchers=[RegexMatcher(r"print\s*\(")],
    file_globs=["**/*.py"],
    diff_only=True,
    message="print() at {file}:{line}",
)
```

When `diff_only=True`, the rule only fires on lines added/modified in the current staged diff. Pre-existing violations on unchanged lines are suppressed. File-level matchers (line 0) always pass through.

Only works with `--staged` (pre-commit hook). When run with `--all` or `--paths`, all lines are checked regardless of `diff_only`.

## Two-phase commit warning flow

WARN-severity rules use a two-phase commit flow so coding agents can self-correct:

1. **First `git commit`** — the hook runs `enforcer check --staged`. WARN findings cause a non-zero exit, blocking the commit and printing the violations + fix instructions.
2. **Agent retries with confirmation** — after addressing or acknowledging the warnings, the agent re-runs:
   ```bash
   ENFORCER_CONFIRM_WARNINGS=1 git commit
   ```
   The hook passes `--confirm-read-warnings`, which acknowledges the WARN findings and allows the commit to proceed.

`enforcer install` drops the hook script (from `scripts/pre-commit-hook`) into `.git/hooks/pre-commit`. The hook honors `ENFORCER_CONFIG` (path to config module) and `ENFORCER_CONFIRM_WARNINGS` env vars.

## MCP server

A minimal MCP server exposes the enforcer over JSON-RPC on stdio. Launch with:

```bash
python -m enforcer.mcp_server
```

Three tools are available:

| Tool | Description |
|------|-------------|
| `check_conventions` | Check files for convention violations. Args: `paths` (optional list; defaults to staged files), `format` (`json` or `text`). |
| `list_conventions` | Return all configured rules as markdown documentation. No args. |
| `verify_fix` | Re-check a single rule on a single file after a fix. Args: `path` (required), `rule_id` (required), `format`. |

The server reads one JSON-RPC message per line from stdin and writes one response per line to stdout. Supports `tools/list` and `tools/call`.

## Available matchers

From `enforcer.matchers`:

| Matcher | Description |
|---------|-------------|
| `RegexMatcher(pattern)` | Find regex matches in file contents. |
| `LineCountMatcher(max_lines=)` | Flag files exceeding a line count. |
| `CharCountMatcher(...)` | Flag files exceeding a character count. |
| `PathNotMatchingMatcher(pattern)` | Flag file paths not matching a glob/regex. |
| `AllowlistMatcher(...)` | Allowlist-based matching with shared context. |
| `AstNodeMatcher(...)` | Match against AST nodes (TS/Python/CSS via tree-sitter). |
| `CommentPerFunctionMatcher(...)` | Comment density per function. |
| `AlwaysMatcher(matched_value=)` | Always matches (useful for advisory rules). |
| `FileExistsMatcher(read_target=)` | Checks whether a file matching the glob exists. |
| `ImportMatcher(forbidden_patterns=)` | Walks AST for import statements, matches against forbidden module regex patterns. Set `needs=AST_PY` or `AST_TS`. |
| `FunctionComplexityMatcher(metric=, max_value=)` | Walks AST functions, computes `lines`/`params`/`nesting`/`cyclomatic` complexity. Emits if over threshold. |
| `PairedFileMatcher(source_glob=, derived_glob=)` | Cross-file: source file staged → derived file (test) must exist. Uses `{stem}` and `{dir}` substitution. |

## Available combinators

From `enforcer.combinators`:

| Combinator | Description |
|------------|-------------|
| `AllOf(matchers)` | All matchers must match. |
| `AnyOf(matchers)` | At least one matcher must match. |
| `OneOf(matchers)` | Exactly one matcher must match. |
| `Not(matcher)` | Negate a single matcher. |
| `NoneOf(matchers)` | No matcher may match. |

## Available predicates

From `enforcer.predicates`:

| Predicate | Description |
|-----------|-------------|
| `IntPredicate(...)` | Compare integer fields of a match. |
| `StringLengthPredicate(...)` | Compare string lengths. |
| `StringMatchesPredicate(pattern)` | Match string fields against a regex. |
| `StringNotMatchesPredicate(pattern)` | Negated string regex match. |
| `All(preds)` | All predicates must pass. |
| `Any(preds)` | At least one predicate must pass. |
| `NotP(pred)` | Negate a predicate. |

## Recipes

### Import graph enforcement

Prevent cross-layer imports (e.g., API layer reaching into jobs layer):

```python
Rule(
    id="api-no-import-jobs",
    severity=Severity.ERROR,
    matchers=[ImportMatcher(forbidden_patterns=[r"app\.jobs\."])],
    file_globs=["backend/app/api/**/*.py"],
    diff_only=True,
    message="API layer imports from app.jobs at {file}:{line}",
    fix_instruction="Move the import to a service module.",
)
```

### Function complexity

Catch god functions before they grow:

```python
Rule(
    id="function-max-lines",
    severity=Severity.WARN,
    matchers=[FunctionComplexityMatcher(metric="lines", max_value=75)],
    file_globs=["backend/app/**/*.py"],
    diff_only=True,
    message="Function at {file}:{line} has {matched_value} lines (max 75)",
    fix_instruction="Extract sub-functions.",
)
```

Metrics: `lines`, `params`, `nesting`, `cyclomatic`.

### Paired file (test coverage)

Enforce that source files have paired test files:

```python
Rule(
    id="test-paired",
    severity=Severity.WARN,
    matchers=[PairedFileMatcher(
        source_glob="backend/app/api/*.py",
        derived_glob="backend/tests/integration/test_{stem}.py",
        exclude_stems=["__init__", "router"],
    )],
    file_globs=["backend/app/api/*.py"],
    diff_only=True,
    message="No test paired with {file}",
    fix_instruction="Create test_{stem}.py",
)
```

`{stem}` = filename without extension. `{dir}` = parent directory name.

## Example config

See [enforcer_config.py](enforcer_config.py) for a complete working example covering raw-hex detection, README line limits, function-focus advisory rules, test-file existence checks, and CSS duplicate advisory.

## Running tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=enforcer
```
