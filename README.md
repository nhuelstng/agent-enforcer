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

1. Create an `enforcer_config.py` at your repo root declaring your rules (see [this repo's own `enforcer_config.py`](enforcer_config.py) for a real working example).

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

### `enforcer sync-doc`

Generate the natural-language conventions markdown from configured rules. Includes rationale for each rule.

| Flag | Description |
|------|-------------|
| `--output FILE` (`-o`) | Write to file (default: `CONVENTIONS.md`). |

```bash
enforcer sync-doc
enforcer sync-doc -o CONVENTIONS.md
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

A list of `Rule` dataclass instances. Key fields: `id`, `severity`, `matchers`, `file_globs`, `exclude_globs`, `message` (supports `{file}`, `{line}`, `{matched_value}`), `fix_instruction`, `diff_only`, `llm_consequence`, `fix`. See `enforcer/rule.py` for the full schema.

```python
Rule(
    id="no-bare-except",
    severity=Severity.ERROR,
    matchers=[RegexMatcher(r"^\s*except\s*:")],
    file_globs=["**/*.py"],
    message="Bare except: at {file}:{line}",
    fix_instruction="Use `except Exception:` or more specific.",
)
```

### `SEVERITY_ACTIONS`

Maps `Severity` to action: `block` (always blocks), `block_warn` (blocks unless `--confirm-read-warnings`), `print`, `hint`.

### `LLM_CONFIG`

```python
LLM_CONFIG = {"concurrency": 5, "timeout": 30}
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

Only works with `--staged` (pre-commit hook). When run with `--all` or `--paths`, `diff_only` rules are suppressed entirely — if there's no diff, "you touched this file" cannot be true.

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

## Severity model

The enforcer uses two severity levels with distinct semantics:

| Severity | Action | Purpose |
|----------|--------|---------|
| `ERROR` | Always blocks commit | Style/correctness rules: naming, tests, complexity, docstrings, imports, secrets, print, bare except. Must fix before commit. |
| `WARN` | Blocks unless `--confirm-read-warnings` | Critical-component reminders: fires when you touch files with broad blast radius (types.py, rule.py, runner.py, etc.). Tells you what to verify before acknowledging. |
| `INFO` | Advisory, never blocks | Informational output. |

### WARN as critical-component reminder

WARN rules fire when you stage changes to files with broad blast radius (types.py, rule.py, runner.py, etc.). Each message tells you what tests to run. Acknowledge with `ENFORCER_CONFIRM_WARNINGS=1 git commit -m "..."`. See `enforcer install` for hook setup.

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

## Available matchers, combinators, predicates

See the [API docs](enforcer/matchers/__init__.py) for the full catalog. Quick reference:

- **Matchers:** `RegexMatcher`, `LineCountMatcher`, `FunctionComplexityMatcher`, `PairedFileMatcher`, `ImportMatcher`, `NamingConventionMatcher`, `DocstringMatcher`, `AlwaysMatcher`, and more.
- **Combinators:** `AllOf`, `AnyOf`, `OneOf`, `Not`, `NoneOf`.
- **Predicates:** `IntPredicate`, `StringLengthPredicate`, `StringMatchesPredicate`, `HasDecoratorPredicate`, `NodeNamePredicate`, plus `All`/`Any`/`NotP` combinators.

## Recipe: Paired file (test coverage)

Enforce that source files have paired test files:

```python
Rule(
    id="test-paired",
    severity=Severity.ERROR,
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

See [enforcer_config.py](enforcer_config.py) for a real working example — this repo enforces its own conventions with 26 rules (19 ERROR for style/correctness + 7 WARN for critical-component reminders, including LLM-analyzed README length).

## CI integration (GitHub Actions)

This repo includes a composite action and workflow for CI. Two scan modes:

| Event | Scope |
|-------|-------|
| Push to feature/fix/refactor/docs/chore branch | Changed files only (diff against `origin/main`) |
| Push to main or PR targeting main | Full repo scan |

The workflow lives at `.github/workflows/enforcer.yml`. The composite action at `.github/actions/enforcer/action.yml` accepts:

| Input | Default | Description |
|-------|---------|-------------|
| `install-method` | `pip` | `skip` \| `pip` \| `wheel` |
| `base-ref` | `""` | Git ref to diff against. Empty = full scan |
| `severity` | `error` | Minimum severity to report |
| `token` | `github.token` | PAT for private repo cross-org checkout |

### Cross-org usage

```yaml
- uses: your-org/pre-commit-agent-enforcer/.github/actions/enforcer@main
  with:
    install-method: pip
    token: ${{ secrets.ENFORCER_PAT }}
    base-ref: origin/main
```

The PAT needs `contents:read` on the enforcer repo. The consuming repo needs `security-events: write` permission for SARIF upload.

## Running tests

```bash
pytest --cov=enforcer
```