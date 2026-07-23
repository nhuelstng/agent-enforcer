# pre-commit-agent-enforcer

Deterministic convention enforcement for coding agents — a composable DSL, CLI, and MCP server that blocks commits violating your project conventions.

## Installation

Editable install (development): `pip install -e .` Or install from the repo: `pip install .`

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

All commands under the `enforcer` entry point.

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

Generate markdown documentation of all configured rules. `--output FILE` (`-o`) writes to file instead of stdout.

### `enforcer sync-doc`

Generate the natural-language conventions markdown from configured rules. Includes rationale for each rule. `--output FILE` (`-o`, default `CONVENTIONS.md`).
```

### `enforcer install`

Install the commit-msg hook into `.git/hooks/commit-msg`.

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

Tunes LLM execution and provider registry. All providers use the OpenAI-compatible
chat-completions API. Set once at the top of `enforcer_config.py` — rules inherit
the defaults unless they override `provider`/`model`.

```python
from enforcer import LLMConfig, ProviderConfig

LLM_CONFIG = LLMConfig(
    default_provider="openai",       # global default, used when rule doesn't override
    default_model="gpt-4o",          # global default model
    concurrency=3,
    timeout=45,
    # providers={...},  # override/add providers (see below)
)
```

```python
# Uses LLM_CONFIG defaults:
llm_consequence=LLMConsequence(prompt="Review this file for conventions.")

# Override per-rule:
llm_consequence=LLMConsequence(prompt="...", provider="anthropic", model="claude-3-5-sonnet-20241022")
```

#### Built-in providers

| Provider | `provider=` | Token env var | Default base URL |
|----------|-------------|--------------|------------------|
| Custom | `"custom"` | `LLM_API_TOKEN` | `https://example.invalid/v1` |
| OpenAI | `"openai"` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| Anthropic | `"anthropic"` | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1` |
| Ollama | `"ollama"` | _(none)_ | `http://localhost:11434/v1` |
| Groq | `"groq"` | `GROQ_API_KEY` | `https://api.groq.com/openai/v1` |
| Mistral | `"mistral"` | `MISTRAL_API_KEY` | `https://api.mistral.ai/v1` |
| DeepSeek | `"deepseek"` | `DEEPSEEK_API_KEY` | `https://api.deepseek.com/v1` |

Reference a provider in `LLMConsequence` or `LLMMatcher`. Omit `provider`/`model` to use the global defaults. Set the token via env var — no code change needed.

#### Custom providers

Add via `LLMConfig.providers` — no source edits:

```python
LLM_CONFIG = LLMConfig(
    default_provider="my-llm",
    default_model="internal-model",
    providers={
        "my-llm": ProviderConfig(
            base_url="https://llm.internal/v1",
            token_env="INTERNAL_LLM_TOKEN",
            headers={"Authorization": "Bearer {token}"},
        ),
    },
)
```

Reference `provider="my-internal-llm"` in any rule. Override a built-in by reusing its key.

#### LLM in CI/CD

Store the token as a repo secret, map to env var in the step:

```yaml
- run: enforcer check --base-ref origin/main
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Or skip LLM entirely with `--no-llm` (the composite action uses this by default).

#### `--no-llm`

Disables all LLM calls. `LLMConsequence` and `LLMMatcher` rules return no matches. Use in CI without secrets, or for fast local runs.

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

Only works with `--staged` (commit-msg hook). When run with `--all` or `--paths`, `diff_only` rules are suppressed entirely — if there's no diff, "you touched this file" cannot be true.

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

| Severity | Action | Purpose |
|----------|--------|---------|
| `ERROR` | Always blocks commit | Style/correctness rules: naming, tests, complexity, docstrings, imports, secrets. Must fix before commit. |
| `WARN` | Blocks unless `--confirm-read-warnings` | Critical-component reminders: fires when you touch files with broad blast radius (types.py, rule.py, runner.py, etc.). Tells you what to verify. |
| `INFO` | Advisory, never blocks | Informational output. |

Acknowledge WARNs with `ENFORCER_CONFIRM_WARNINGS=1 git commit -m "..."` or `enforcer check --confirm-read-warnings`. See `enforcer install` for hook setup.

## MCP server

A minimal MCP server exposes the enforcer over JSON-RPC on stdio. Launch with `python -m enforcer.mcp_server`. Three tools: `check_conventions` (args: `paths`, `format`), `list_conventions` (no args), `verify_fix` (args: `path`, `rule_id`, `format`). Supports `tools/list` and `tools/call`.

## Available matchers, combinators, predicates

See [`enforcer/matchers/__init__.py`](enforcer/matchers/__init__.py) for the full catalog. Quick reference: matchers (`RegexMatcher`, `LineCountMatcher`, `FunctionComplexityMatcher`, `PairedFileMatcher`, `ImportMatcher`, `NamingConventionMatcher`, `DocstringMatcher`, `AlwaysMatcher`, `LLMMatcher`, …), combinators (`AllOf`, `AnyOf`, `OneOf`, `Not`, `NoneOf`), predicates (`IntPredicate`, `StringLengthPredicate`, `StringMatchesPredicate`, `HasDecoratorPredicate`, `HasAttributePredicate`, `NodeNamePredicate`, plus `All`/`Any`/`NotP`).

## Recipe: Paired file (test coverage)

Enforce that source files have paired test files via `PairedFileMatcher(source_glob=..., derived_glob="test_{stem}.py")`. See [`enforcer_config.py`](enforcer_config.py) for working examples.

## Recipe: Architecture boundaries

`ArchitectureMatcher` reads the import graph and flags forbidden imports. Declare a layer DAG (`layers` + `allowed_edges`, with `forbid_implicit=True`), and/or `isolate_siblings` — parent dirs whose immediate children are peer slices that may not import each other (the vertical-slice "no cross-slice imports" invariant a flat layer can't express, since sibling slices collapse to one layer). Both share one import-graph pass — Python (dotted imports; map a subdirectory-rooted package with `SOURCE_ROOTS = {"app": "backend/app"}` so `app.*` resolves at the repo root) and TypeScript/JS (relative `./` / `../` imports; bare and aliased specifiers are treated as external). `DeepImportBarrierMatcher(module_glob="pkg/*", entry_points=["__init__.py"])` complements it on the same graph — it governs *where* a permitted crossing may land: imports into a module must hit an `entry_point`, not reach into internals (symbol-agnostic, no allowlist).

```python
ArchitectureMatcher(isolate_siblings=["app/features"])
# app/features/orders/... -> app/features/billing/... flagged;  -> app/shared/... allowed
```

## Recipe: C# / ASP.NET Core conventions

Set `needs=Needs.AST_CSHARP` on any AST matcher to check `.cs` files (`DocstringMatcher`, `NamingConventionMatcher`, `FunctionComplexityMatcher`, `ImportMatcher`, `AstNodeMatcher`, `MagicNumberMatcher`, `InterfaceMatcher`, `InvocationMatcher`, `AsyncMethodMatcher`, and the namespace-graph matchers `ArchitectureMatcher`/`DeepImportBarrierMatcher`/`CycleMatcher`). Attribute/base-type/argument predicates filter matches by the C# declaration they land on — the enablers for attribute-driven ASP.NET rules. Compose `AstNodeMatcher(node_type="class_declaration")` with `NodeNamePredicate(pattern=r"Controller$")` and: `NotP(HasAttributePredicate(pattern=r"Authorize|AllowAnonymous"))` (require `[Authorize]`), `NotP(HasBaseTypePredicate(pattern=r"ControllerBase"))` (must derive `ControllerBase`), or `NotP(AttributeArgumentPredicate(attribute="Route"))` (require a `[Route(...)]` template). `InvocationMatcher(pattern=r"\.Wait$")` bans sync-over-async calls; `AsyncMethodMatcher(check="no_async_void")` and `AsyncMethodMatcher(check="task_suffix")` enforce async conventions. A ready-to-copy **security-by-default** rule set (mandatory `[Authorize]` on every controller unless it opts out with `[AllowAnonymous]`) lives in [`examples/aspnet_security.py`](examples/aspnet_security.py). `CsprojProps` extracts `<PropertyGroup>` names and `PackageReference` ids so `KeySetSyncMatcher` can require project properties (`Nullable`, `TreatWarningsAsErrors`) or keep `Directory.Packages.props` in sync. See [`AGENTS.md`](AGENTS.md#language-support) for C# node-type specifics.

## Example config

See [enforcer_config.py](enforcer_config.py) for a real working example — this repo enforces its own conventions with 26 rules (19 ERROR for style/correctness + 7 WARN for critical-component reminders, including LLM-analyzed README length).

## CI integration (GitHub Actions)

Composite action at `.github/actions/enforcer/action.yml`, workflow at `.github/workflows/enforcer.yml`. Two scan modes: feature-branch pushes diff against `origin/main`; pushes to main / PRs do a full scan.

Composite action inputs: `install-method` (`pip`|`wheel`|`skip`, default `pip`), `base-ref` (git ref, empty = full scan), `severity` (default `error`), `token` (default `github.token`; use a PAT for cross-org private repos).

### Cross-org usage

Reference the action as `nhuelstng/agent-enforcer/.github/actions/enforcer@main` with `token: ${{ secrets.ENFORCER_PAT }}` and `base-ref: origin/main`. The PAT needs `contents:read` on the enforcer repo; the consuming repo needs `security-events: write` for SARIF upload.

## Running tests

```bash
pytest --cov=enforcer
```