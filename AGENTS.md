# AGENTS.md

Convention enforcement tool for coding agents. This file defines the rules and contracts that any AI agent (or human) must follow when working in this repo.

> Auto-generated rule list: see `CONVENTIONS.md` (run `enforcer sync-doc` to regenerate).

## Project Overview

`pre-commit-agent-enforcer` is a deterministic convention enforcement tool for coding agents. It provides a composable DSL, CLI, and MCP server that blocks commits violating project conventions. Matchers find violations, predicates filter them, rules compose them, and the runner executes them against files.

## Domain Vocabulary

An agent must use these terms correctly in code, commits, and discussion:

- **Rule** — composes matchers + predicates + message into a checkable unit. Defined in `enforcer/rule.py`.
- **Matcher** — finds violations in file content, returns `list[Match]`. Each matcher is a dataclass with a `find()` method.
- **Predicate** — filters `Match` objects (post-matcher, pre-message). Applied in `Rule.check()`.
- **Combinator** — combines matchers (AllOf, AnyOf, Not, NoneOf, OneOf). Defined in `enforcer/combinators/core.py`.
- **FileContext** — per-file parsed state: raw text, optional AST, changed_lines. Built once, reused by all matchers.
- **shared_ctx** — cross-file dict passed to every `matcher.find()`. Used for cross-file reference data (allowlists, paired files, duplicate detection).
- **Needs** — enum declaring what a matcher requires: `RAW`, `AST_PY`, `AST_TS`, `AST_CSS`. Drives parse-once caching.
- **Severity** — `ERROR` (style/correctness, always blocks), `WARN` (critical-component reminder, blocks unless `--confirm-read-warnings`), `INFO` (advisory).
- **RuleType** — `CONTENT` (checked per-file) vs `METADATA` (checked once per run, e.g. branch name, commit message).
- **LLMMatcher** — matcher that calls an LLM as the check itself. Returns `Match` objects from structured JSON verdicts. Composes via combinators like any matcher. Defined in `enforcer/matchers/llm_check.py`.
- **ChangeContext** — carries change metadata (commit message, branch, created/modified/deleted/renamed file lists). Stored in `shared_ctx["__change__"]`. Read by METADATA-phase and finalizer matchers. Defined in `enforcer/types.py`.
- **FileContext.status** — per-file event kind: `"added"`, `"modified"`, `"deleted"`, `"renamed"`. Populated from `git diff --name-status`. Default `"modified"`. Existing matchers ignore it; event-aware matchers check it.
- **Extractor** — pure string→set transform (e.g. `EnvFileKeys`, `TerraformBlockKeys`). Used by `KeySetSyncMatcher` to compare key sets across files. Defined in `enforcer/extractors/core.py`.

## Branch Convention

Branch names must match `type/description`:
- `feature/<slug>` — new features
- `fix/<slug>` — bug fixes
- `docs/<slug>` — documentation changes
- `refactor/<slug>` — code refactoring
- `chore/<slug>` — tooling, dependencies, cleanup

Never commit to `master` directly. Create a feature branch first.

```bash
git checkout -b feature/add-new-matcher
```

## Commit Convention

Conventional Commits format:

```
type(scope): description

feat(matchers): add DocstringMatcher for public function docs
fix(cli): handle empty file list in --staged mode
docs(readme): update self-enforcement example
refactor(cli): extract check() into focused functions
chore(hygiene): untrack pyc files, dedupe gitignore
```

Two-commit convention for review feedback: create a fixup commit, do not amend. This preserves review history.

## Testing Minimum Bar

Every new matcher, predicate, or combinator ships with paired tests:
- Matchers: `tests/test_matchers/test_<name>.py`
- Predicates: `tests/test_predicates/test_<name>.py`
- Combinators: `tests/test_combinators/test_<name>.py`
- Core modules: `tests/test_<name>.py`

Run `pytest` before committing. The enforcer's `core-test-paired` rule will flag missing tests.

```bash
pytest --tb=short -q
```

## Matcher Development Contract

Every matcher must implement this interface:

```python
@dataclass
class MyMatcher:
    needs: Needs = Needs.RAW  # or AST_PY, AST_TS, AST_CSS

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        ...
```

Rules:
1. **`find()` signature:** `(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]`
2. **Declare `needs`:** class attribute, drives parse-once caching
3. **Accept `shared_ctx=None`:** defensive default, matchers may be called standalone
4. **No try/except around core logic:** let errors propagate. Only catch around external calls (git, httpx) where you return empty on failure.
5. **Iterative DFS for AST walks:** never recursive. Precedent: `import_matcher.py:44`. Deep ASTs will hit Python's recursion limit.
6. **Two-phase matchers:** if cross-file analysis is needed, `find()` collects into `shared_ctx`, `finalize_duplicates()` emits matches after all files processed. See `duplicate_code.py`.

## Rule Authoring Guide

Rules live in `enforcer_config.py`:

```python
Rule(
    id="my-rule-id",           # stable identifier
    severity=Severity.ERROR,   # ERROR (style, blocks), WARN (reminder, blocks unless confirmed), INFO (advisory)
    matchers=[MyMatcher()],     # one matcher, or use combinators for multiple
    file_globs=["**/*.py"],     # which files to check
    exclude_globs=["**/test*"], # skip these
    message="...",              # {file}, {line}, {matched_value} placeholders
    fix_instruction="...",      # actionable hint for agents
    diff_only=True,             # only check changed lines (--staged); suppressed entirely on --all/--paths
    rule_type=RuleType.CONTENT, # CONTENT (per-file) or METADATA (once)
)
```

Guidelines:
- One matcher per rule when possible. Use combinators (`AllOf`, `AnyOf`) for multi-matcher.
- Always set `fix_instruction` — agents need actionable fix hints.
- Use `diff_only=True` for rules that only matter on changed lines. Suppressed entirely on `--all`/`--paths` (no diff = not touched).
- Use `read_targets` for cross-file reference data (allowlists, config files).
- Message templates support `{file}`, `{line}`, `{column}`, `{matched_value}`.
- **Severity choice:** `ERROR` for all style/correctness rules (naming, tests, complexity, docstrings, imports, secrets). `WARN` only for critical-component reminders — fires when you touch files with broad blast radius (types.py, rule.py, runner.py, etc.). The message should tell the agent what to verify.

## Architecture Map

```
enforcer/
  types.py        — core types (Severity, Needs, RuleType, Match, FileContext, LLMConsequence)
  rule.py         — Rule dataclass + glob matching (_glob_match)
  runner.py       — RuleRunner: applies rules to files, severity filtering, finalizers
  context.py      — FileContextBuilder: parse-once cache, lazy AST population
  config.py       — loads enforcer_config.py via importlib
  cli.py          — check, docs, install commands (Click)
  reporter.py     — text, JSON, SARIF output + exit code computation
  fix.py          — auto-fix infrastructure
  ignore.py       — .enforcerignore loading and matching
  llm.py          — LLMExecutor: calls LLM provider on rule failure
  docs.py         — markdown rule documentation generator
  mcp_server.py   — MCP server interface
  matchers/       — 20 matchers, each in own file (incl. KeySetSyncMatcher)
  predicates/     — post-match filters (AST, string, int, combinators)
  combinators/    — matcher combiners (AllOf, AnyOf, Not, NoneOf, OneOf, StatusGate)
  extractors/     — key-set extractors (env, json, yaml, ini, terraform)
  parsers/         — tree-sitter parser + language detection
tests/
  test_matchers/  — paired tests for each matcher
  test_predicates/— paired tests for each predicate
  test_combinators/ — paired tests for each combinator
```

## Adding a New Matcher

1. Create `enforcer/matchers/<name>.py`
2. Implement `find()` with `shared_ctx=None` default
3. Set `needs` class attribute
4. Add to `enforcer/matchers/__init__.py` `__all__`
5. Write `tests/test_matchers/test_<name>.py`
6. Add a Rule to `enforcer_config.py` if self-enforcing
7. Run `pytest` — all tests must pass

## Config Injection Contract

`load_config()` (in `enforcer/config.py`) executes `enforcer_config.py` as a Python module via `importlib`. It extracts four module-level attributes:

- `RULES` — `list[Rule]`, ordered list of convention rules
- `WORKSPACE` — `str`, root directory for path resolution (default `"."`)
- `SEVERITY_ACTIONS` — `dict[Severity, str]`, maps severity to action
- `LLM_CONFIG` — `dict`, LLM execution tuning

The config file is plain Python, not YAML/TOML. This allows full expressiveness (functions, imports, conditionals) at the cost of requiring Python to parse it.

## Self-Enforcement

This repo enforces its own conventions. The commit-msg hook is installed at `.git/hooks/commit-msg` and runs `enforcer check --staged` on every commit.

To install (one-time):
```bash
python -m enforcer.cli install --force
```

The config has 25 rules: 18 ERROR (style/correctness — always block) + 7 WARN (6 critical-component reminders + 1 LLM sanity check — block unless acknowledged). WARN rules fire when you stage changes to files with broad blast radius (`types.py`, `rule.py`, `runner.py`, `context.py`, `config.py`, `parsers/`), or run an LLM-based commit-message alignment check. Each WARN tells you what tests to run before acknowledging:
```bash
ENFORCER_CONFIRM_WARNINGS=1 git commit -m "..."
```

The self-enforcement config lives in `enforcer_config.py` at the repo root.
