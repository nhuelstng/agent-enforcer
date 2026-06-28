# Dogfooding: Self-Enforcement Design

**Date:** 2026-06-28
**Status:** Approved (all 6 sections)
**Approach:** C — Graduated Enforcement

## Goal

Dogfood the enforcer tool on this repo. Make `pre-commit-agent-enforcer` a prime example of good AI agent coding: real self-enforcement config, AGENTS.md with agent coding conventions, hook installed on itself, repo hygiene clean, targeted refactors.

## Context

- 102 Python files, 280 tests passing, 16 matchers
- No `AGENTS.md` or `CLAUDE.md` exists — no agent guidance
- Root `enforcer_config.py` is an Angular/TS demo — no-op on this Python codebase
- `examples/asml_enforcer_config.py` (403 lines) is config for a different repo
- `.gitignore` has triplicate `.coverage` entries
- 5 `.pyc` files tracked in `tests/test_predicates/__pycache__/`
- No pre-commit hook installed on itself

Current violations against proposed rules (verified):
- 39/61 public functions missing docstrings
- `llm.py:60` has `print()` call (ERROR-level violation)
- `cli.py:check()` — 88 lines, CC=23, 11 params (worst offender)
- `rule.py:check()` — CC=12
- `reporter.py:_render_text` — CC=11
- `ignore.py:_match_pattern` — CC=11
- 2 functions >75 lines (`mcp_server.py:run_mcp_server` 106 lines, `cli.py:check` 88 lines)
- 2 functions >5 params (`cli.py:check` 11 params, `runner.py:__init__` 6 params)
- No wildcard imports (clean), no bare except (clean), all classes CapWords (clean)

## Section 1: Repo Hygiene Cleanup

- `.gitignore`: deduplicate 3 `.coverage` entries to 1
- Untrack 5 `.pyc` files in `tests/test_predicates/__pycache__/` (`git rm --cached`)
- Remove `enforcer_config.py` (Angular/TS demo, replaced by real self-config in Phase 3)
- Remove `examples/asml_enforcer_config.py` (belongs in ASML repo)
- Delete `examples/` directory entirely
- Remove `tests/test_asml_config_updates.py` (tests the removed ASML config)
- Update `README.md` — remove references to removed config

Stays: `README.md`, `docs/superpowers/specs/`, `scripts/pre-commit-hook`, `pyproject.toml`

## Section 2: AGENTS.md

ASML-style detailed, adapted to this repo's domain. ~150-200 lines, 10 sections:

1. **Project Overview** — one paragraph: what the enforcer is (deterministic convention enforcement for coding agents), three interfaces (DSL, CLI, MCP server)

2. **Domain Vocabulary** — core nouns an agent must use correctly:
   - `Rule` — composes matchers + predicates + message into a checkable unit
   - `Matcher` — finds violations in file content, returns `list[Match]`
   - `Predicate` — filters `Match` objects (post-matcher, pre-message)
   - `Combinator` — combines matchers (AllOf, AnyOf, Not, etc.)
   - `FileContext` — per-file parsed state (raw text, AST, changed_lines)
   - `shared_ctx` — cross-file dict passed to every `matcher.find()`
   - `Needs` — declares what a matcher requires (RAW, AST_PY, AST_TS, AST_CSS)
   - `Severity` — ERROR (block), WARN (block unless confirmed), INFO (advisory)
   - `RuleType` — CONTENT (per-file) vs METADATA (once per run)

3. **Branch Convention** — `type/description` (feature/, fix/, docs/, refactor/, chore/). Never commit to master directly.

4. **Commit Convention** — Conventional Commits: `type(scope): description`. Two-commit convention when addressing review feedback (fixup commit, not amend).

5. **Testing Minimum Bar** — every new matcher, predicate, or combinator ships with paired tests in `tests/test_matchers/`, `tests/test_predicates/`, or `tests/test_combinators/`. Run `pytest` before committing. 280 tests is the floor.

6. **Matcher Development Contract** — interface every matcher must implement:
   - `find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]`
   - Declare `needs: Needs` as class attribute
   - Accept `shared_ctx=None` (defensive default)
   - Two-phase matchers: `find()` collects into shared_ctx, `finalize_duplicates()` emits cross-file matches
   - No try/except around core logic — let errors propagate
   - Iterative DFS for AST walks (not recursive) — precedent: `import_matcher.py:44`

7. **Rule Authoring Guide** — how to write a `Rule` in `enforcer_config.py`:
   - One matcher per rule when possible; use combinators for multi-matcher
   - Always set `fix_instruction` — agents need actionable fix hints
   - Use `diff_only=True` for rules that only matter on changed lines
   - Use `read_targets` for cross-file reference data (allowlists, configs)
   - Message templates: `{file}`, `{line}`, `{matched_value}` placeholders

8. **Architecture Map** — file-level guide:
   - `enforcer/types.py` — core types, don't add fields without updating all matchers
   - `enforcer/rule.py` — Rule dataclass + glob matching
   - `enforcer/runner.py` — RuleRunner, severity filtering, finalizers
   - `enforcer/context.py` — FileContextBuilder, parse-once cache
   - `enforcer/config.py` — loads enforcer_config.py via importlib
   - `enforcer/cli.py` — check/docs/install commands
   - `enforcer/matchers/` — matchers, each in own file
   - `enforcer/predicates/` — post-match filters
   - `enforcer/combinators/` — matcher combiners
   - `enforcer/parsers/` — tree-sitter + language detection

9. **Adding a New Matcher** — checklist:
   - Create `enforcer/matchers/<name>.py`
   - Implement `find()` with `shared_ctx=None` default
   - Set `needs` class attribute
   - Add to `enforcer/matchers/__init__.py` `__all__`
   - Write `tests/test_matchers/test_<name>.py`
   - Add example Rule to `enforcer_config.py` if self-enforcing

10. **Config Injection Contract** — `load_config()` executes `enforcer_config.py` as a module, extracts `RULES`, `WORKSPACE`, `SEVERITY_ACTIONS`, `LLM_CONFIG`. Config file is plain Python, not YAML/TOML.

## Section 3: Self-Enforcement Rules

17 rules total. 16 use existing matchers. 1 requires new `DocstringMatcher`.

### Mirror rules (13)

| # | ID | Severity | Matcher | Glob | Notes |
|---|---|---|---|---|---|
| 1 | `branch-naming` | ERROR | BranchNameMatcher | `*` (METADATA) | `^(feature\|fix\|hotfix\|chore\|docs\|refactor)/` |
| 2 | `commit-message` | WARN | CommitMessageMatcher | `*` (METADATA) | Conventional Commits |
| 3 | `matcher-test-paired` | WARN | PairedFileMatcher | `enforcer/matchers/*.py` | → `tests/test_matchers/test_{stem}.py`, exclude `__init__`, diff_only |
| 4 | `predicate-test-paired` | WARN | PairedFileMatcher | `enforcer/predicates/*.py` | → `tests/test_predicates/test_{stem}.py`, diff_only |
| 5 | `combinator-test-paired` | WARN | PairedFileMatcher | `enforcer/combinators/*.py` | → `tests/test_combinators/test_{stem}.py`, diff_only |
| 6 | `core-test-paired` | WARN | PairedFileMatcher | `enforcer/*.py` | → `tests/test_{stem}.py`, exclude `__init__`, diff_only |
| 7 | `function-snake-case` | WARN | NamingConventionMatcher | `enforcer/**/*.py` | `function_definition`, pattern `^[a-z_]`, diff_only |
| 8 | `no-print` | ERROR | RegexMatcher | `enforcer/**/*.py` | `^\s*print\s*\(` — fix `llm.py` to use `sys.stderr.write` |
| 9 | `no-bare-except` | ERROR | RegexMatcher | `enforcer/**/*.py` | `^\s*except\s*:` |
| 10 | `no-secrets` | ERROR | RegexMatcher | `**/*.py` | Standard secret pattern |
| 11 | `function-max-lines` | WARN | FunctionComplexityMatcher | `enforcer/**/*.py` | metric=lines, max=75, diff_only, exclude cli.py (Click command) |
| 12 | `function-max-params` | WARN | FunctionComplexityMatcher | `enforcer/**/*.py` | metric=params, max=5, diff_only, exclude cli.py (Click options) |
| 13 | `todo-needs-owner` | WARN | RegexMatcher | `enforcer/**/*.py` | `#\s*(TODO\|FIXME)\b(?!\s*\(@)` |

### Stretch rules (4)

| # | ID | Severity | Matcher | Notes |
|---|---|---|---|---|
| 14 | `no-wildcard-imports` | WARN | ImportMatcher | forbidden `[r"import\s+\*"]`, diff_only |
| 15 | `cyclomatic-complexity` | WARN | FunctionComplexityMatcher | metric=cyclomatic, max=10, diff_only, exclude cli.py |
| 16 | `class-capwords` | WARN | NamingConventionMatcher | `class_definition`, pattern `^[A-Z]`, diff_only |
| 17 | `docstring-public` | WARN | **DocstringMatcher** (new) | Walks AST for `function_definition`, skips `_`-prefixed and `__init__`, flags if no docstring. diff_only |

### cli.py exclusions

`cli.py:check()` has CC=23, 11 params, 88 lines — but it's a Click command where `@click.option` decorators inject parameters. Framework artifact, not real complexity. Excluded from complexity/params rules.

### DocstringMatcher design

~30 lines, walks tree-sitter Python AST for `function_definition` nodes. Checks if first child statement is a string literal. Excludes `_`-prefixed (private) and `__init__`. The tool grows a feature to enforce its own conventions — ultimate dogfood.

### Severity actions

```python
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
```

### Current violations this config would catch

- 39/61 public functions missing docstrings (WARN)
- `llm.py:60` print() call (ERROR)
- `cli.py:check()` — 88 lines, 11 params, CC=23 (excluded from complexity but not from other rules)
- `rule.py:check()` — CC=12 (WARN)
- `reporter.py:_render_text` — CC=11 (WARN)
- `ignore.py:_match_pattern` — CC=11 (WARN)
- 2 functions >75 lines (WARN)
- 2 functions >5 params (WARN, cli.py excluded)

## Section 4: Pre-commit Hook Installation

- Run `enforcer install` — copies `scripts/pre-commit-hook` to `.git/hooks/pre-commit`
- Hook runs `python -m enforcer.cli check --staged --config enforcer_config.py`
- WARN rules block unless `ENFORCER_CONFIRM_WARNINGS=1` is set (the `--confirm-read-warnings` flag)

### Transition period

First commit after adding config + hook will be blocked by its own rules:
- 39 functions missing docstrings (WARN, block_warn)
- `llm.py` print() (ERROR, blocks)
- `rule.py:check()` CC=12 (WARN, block_warn)

Resolution: config commit lands via `ENFORCER_CONFIRM_WARNINGS=1`. Follow-up commit fixes ERROR-level violations (print → sys.stderr). WARN-level debt (docstrings, complexity) paid down incrementally with `--confirm-read-warnings` as escape hatch until debt cleared.

No new matchers needed for this section. Hook script already exists and works.

## Section 5: Architectural Refactors

Minimal, targeted. Repo already well-structured (102 files, all under 200 lines except mcp_server at 193). No sweeping restructures.

### Refactor 1: Extract `cli.py:check()` (88 lines, CC=23, 11 params)

Click callback — decorators inflate param count (unavoidable). But 88-line body and CC=23 are real. Extract into focused functions:

- `_collect_files(staged, all_files, paths, ws) -> list[str]` — file discovery logic (lines 70-89)
- `_build_shared_ctx(config, builder, ws) -> dict` — read_targets loading (lines 108-117)
- `_run_checks(runner, builder, file_list, shared_ctx, ws, staged) -> list[Match]` — per-file check loop (lines 119-127)
- `check()` becomes orchestration only — call collectors, runner, reporter (~20 lines)

Reduces CC from 23 to ~5 in the main function. Extracted functions are independently testable.

### Refactor 2: Remove `llm.py` print() → sys.stderr.write

One line. `llm.py:60` has `print(f"[enforcer] LLM call failed: {e}", file=sys.stderr)`. Replace with `sys.stderr.write(f"[enforcer] LLM call failed: {e}\n")`. Already imports `sys`.

### Refactor 3: Fix `.gitignore` duplicates

Current:
```
.coverage
.coverage
.coverage
```

Replace with:
```
.coverage
```

Already has `__pycache__/` and `*.pyc` — just deduplicate `.coverage`.

### Refactor 4: Untrack `__pycache__` artifacts

`git rm --cached tests/test_predicates/__pycache__/*.pyc` (5 files). Already gitignored, remove from tracking.

### What we explicitly do NOT refactor

- `mcp_server.py` (193 lines, CC=10 on `run_mcp_server`) — within limits, one cohesive function
- `reporter.py:_render_text` (CC=11) — borderline; flagged by cyclomatic rule but not refactored now. Rule catches it; fix when someone touches that file next.
- `rule.py:check()` (CC=12) — borderline; same logic. Flagged by the rule, fixed when next touched.
- Matcher file structure — flat and clean. No change.
- `types.py` — small, focused. No change.

Ponytail: don't refactor what you're not already changing.

### Net result

cli.py becomes orchestration-only, one print() removed, gitignore cleaned, pyc untracked. ~4 files touched. No new abstractions, no new files (except DocstringMatcher from Section 3).

## Section 6: Implementation Order

Sequenced so each step is independently committable and the repo stays green.

### Phase 1: Hygiene (no rule changes)

1. Fix `.gitignore` — deduplicate `.coverage`
2. `git rm --cached` the 5 tracked `.pyc` files
3. Remove `enforcer_config.py` (Angular demo)
4. Remove `examples/asml_enforcer_config.py` + `examples/` dir
5. Remove `tests/test_asml_config_updates.py`
6. Update `README.md` — remove references to removed config

Commit: `chore: repo hygiene — untrack pyc, dedupe gitignore, remove ASML example config`

### Phase 2: DocstringMatcher

7. Create `enforcer/matchers/docstring.py` (~30 lines)
8. Add to `enforcer/matchers/__init__.py` `__all__`
9. Write `tests/test_matchers/test_docstring.py`

Commit: `feat: DocstringMatcher — flag public functions missing docstrings`

### Phase 3: Self-enforcement config

10. Write new `enforcer_config.py` (17 rules from Section 3)
11. Run `enforcer check --all --config enforcer_config.py` — see what fires
12. Fix `llm.py:60` print() → `sys.stderr.write` (ERROR violation)
13. Run `enforcer check --all` again — confirm no ERROR violations remain

Commit: `feat: self-enforcement config — 17 rules for agent coding conventions`

### Phase 4: AGENTS.md

14. Write `AGENTS.md` (10 sections from Section 2)
15. Commit with `ENFORCER_CONFIRM_WARNINGS=1` (AGENTS.md has no docstrings to violate, but branch/commit conventions apply)

Commit: `docs: AGENTS.md — agent coding conventions and matcher development contract`

### Phase 5: Architectural refactors

16. Extract `cli.py:check()` into focused functions
17. Run `pytest` — confirm 280+ tests still pass
18. Run `enforcer check --all` — confirm refactored cli.py doesn't trigger complexity rules

Commit: `refactor: extract cli.check() into focused functions — CC 23→5`

### Phase 6: Install hook

19. Run `enforcer install`
20. Verify `.git/hooks/pre-commit` exists and is executable
21. Make a test commit with `ENFORCER_CONFIRM_WARNINGS=1` to confirm the loop works

Commit: `chore: install self-enforcement hook`

### Debt tracked by WARN rules (not blocking, fix incrementally)

- 39 functions missing docstrings — pay down as files are touched
- `rule.py:check()` CC=12 — refactor when next touched
- `reporter.py:_render_text` CC=11 — refactor when next touched
- `ignore.py:_match_pattern` CC=11 — refactor when next touched

## File Change Summary

**New files:**
- `AGENTS.md`
- `enforcer/matchers/docstring.py`
- `tests/test_matchers/test_docstring.py`
- `enforcer_config.py` (replaced with real self-config)

**Deleted:**
- `enforcer_config.py` (old Angular demo)
- `examples/asml_enforcer_config.py`
- `examples/` directory
- `tests/test_asml_config_updates.py`
- 5 `.pyc` files in `tests/test_predicates/__pycache__/`

**Modified:**
- `.gitignore`
- `README.md`
- `enforcer/llm.py`
- `enforcer/cli.py`
- `enforcer/matchers/__init__.py`

~10 files touched total. No changes to `Rule`, `FileContext`, `Config`, `RuleRunner`, or `types.py`.
