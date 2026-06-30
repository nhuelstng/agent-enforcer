# Rule Clarity — `explain` command + docstring/test conventions

**Status:** Approved (brainstorm 2026-06-30)
**Scope:** Foundational. Unblocks the four AI-pattern matchers (separate spec).
**Author:** brainstorming session

## Problem

The rule DSL is opaque. Reading `Rule(matchers=[RegexMatcher(r"^\s*print\s*\(")])` inside `enforcer_config.py` does not tell you:

1. What the matcher catches (intent, edge cases, what it ignores).
2. What a violating input looks like, or what a clean case looks like.
3. Why the rule exists beyond the one-line `rationale` string.

Agents at commit time face the same wall: the `Match` payload gives location + message + fix instruction, but nothing on *why* the matcher fired or what the matcher's scope is. The result is rote fix-application without understanding, and a config author who can't audit their own rules by glancing at them.

The docs generator (`enforcer/docs.py`) renders rule metadata (id, severity, globs, message, fix, rationale) but does not surface matcher-level detail — class docstrings, paired test paths, worked examples. The information exists; it is not assembled.

## Goal

Make a rule self-explanatory: a human or agent can answer "what does this rule match, what does it ignore, what does a violation look like" without reading matcher source. Achieve this by:

- Establishing docstring conventions for all matchers (what / ignores / basis / shared_ctx).
- Surfacing those docstrings + paired-test structure via a new `enforcer explain <rule-id>` command.
- Treating paired test files as the canonical worked-example catalog (well-named, docstring-per-scenario).

No new fields on `Rule` or matcher dataclasses. No config breakage. Pure reflection over what's already there.

## Non-Goals

- New matchers (separate spec).
- Fluent/builder DSL rewrite (cosmetic, rejected).
- YAML config format (loses Python expressiveness).
- Per-rule `examples` field (rejected — tests are the example catalog, avoids duplication and drift).

## Design

### Part 1 — Docstring conventions for matchers

Every matcher module and class already has a one-line docstring (e.g. `regex.py:10`). Extend to a structured multi-part docstring without changing the dataclass shape:

**Module docstring** (one line, existing): what the matcher finds.
```python
"""RegexMatcher: finds regex pattern matches in file text."""
```

**Class docstring** (structured, new convention). Four labeled sections, separated by blank lines, all optional except `What`:

```
What:      <one line — what this matcher flags>
Ignores:   <one line — what it deliberately does NOT catch, or "n/a">
Basis:     <RAW | AST_PY | AST_TS | AST_CSS | regex | cross-file> — what input it operates on
shared_ctx: <keys read/written, or "none">
```

Example — `RegexMatcher`:

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

Convention is enforced by the repo's own `core-test-paired` / docstring rules on `diff_only` changes — touching a matcher means updating its docstring. New self-enforcement rule `matcher-docstring-structured` (ERROR, diff_only) checks every matcher class docstring contains a `What:` line; fires on `enforcer/matchers/*.py` changes only.

### Part 2 — Paired test files as worked-example catalog

Existing convention: `tests/test_matchers/test_<name>.py` for each matcher. No new infrastructure. Add organizational convention:

**Test file structure** (convention, not enforced field):

```python
"""Tests for RegexMatcher.

Covers: line matching, column offsets, redact mode, empty/multiline input.
"""
from enforcer.matchers.regex import RegexMatcher

class TestRegexMatcherLineMatches:
    """flags a line that fully matches the pattern."""

    def test_print_call_flagged(self):
        # input -> expected match
        ctx = make_ctx("print('hi')\n")
        matches = RegexMatcher(r"^\s*print\s*\(").find(ctx)
        assert len(matches) == 1
        assert matches[0].line == 1

class TestRegexMatcherRedact:
    """redact=True replaces matched value with ***REDACTED***."""

    def test_secret_redacted(self):
        ...
```

Convention rules:
- One test class per scenario (what's being asserted), descriptive name.
- Class docstring is the scenario label.
- Test method names read as the assertion ("print_call_flagged", "secret_redacted").
- First test in each class is the canonical example — the one `explain` will surface.

**Positive + negative coverage (enforced).** Every matcher test file MUST contain both:

- **Positive case** (rule fires when it should): test method named `test_*_fail` (or `test_*_flags` / `test_*_violation`), body uses `assert` on a non-empty match list (e.g. `assert len(matches) >= 1`). Parameterized with **≥3 examples** via `@pytest.mark.parametrize`.
- **Negative case** (rule does NOT fire when it shouldn't): test method named `test_*_success` (or `test_*_clean` / `test_*_valid`), body uses `assert not` or `assert len(matches) == 0`. Parameterized with **≥3 examples**.

Minimum: 2 parameterized methods × 3 examples = 6 cases per matcher. More scenarios welcome; the floor is positive + negative, each with 3 inputs.

```python
import pytest

class TestRegexMatcherFlags:
    """flags lines that match the configured pattern."""

    @pytest.mark.parametrize("line", [
        "print('hi')",           # bare print
        "    print('indented')",  # indented
        "\tprint('tabbed')",     # tab-indented
    ])
    def test_print_flagged(self, line):
        ctx = make_ctx(line + "\n")
        matches = RegexMatcher(r"^\s*print\s*\(").find(ctx)
        assert len(matches) == 1

class TestRegexMatcherClean:
    """does not flag lines that don't match."""

    @pytest.mark.parametrize("line", [
        "x = 1",                  # no print
        "sprint('hi')",          # word containing 'print' but not a call
        "# print('commented')",  # commented out
    ])
    def test_no_match(self, line):
        ctx = make_ctx(line + "\n")
        matches = RegexMatcher(r"^\s*print\s*\(").find(ctx)
        assert not matches
```

Enforced by new self-enforcement rule `matcher-test-positive-negative` (ERROR, diff_only) — see Part 5.

Existing test files get retrofit as they're touched (diff_only).

### Part 3 — `enforcer explain <rule-id>` command

New CLI command. Pure reflection, no execution of rules against files.

```
enforcer explain <rule-id> [--config enforcer_config.py]
```

**Output** (text by default, `--format json` supported):

```
Rule: no-print
Severity: ERROR (blocks)
Applies to: enforcer/**/*.py  (content rule, per-file)
Diff-only: yes (fires only on --staged changed lines)

Message: print() found in library code at {file}:{line}. Use sys.stderr.write or structlog.
Fix:     Replace print() with sys.stderr.write(...).
Why:     print() writes to stdout, which is reserved for machine-readable output in CLI tools...

Matchers (1):
  1. RegexMatcher
     What:       flags any line where `pattern` matches at least once
     Ignores:    multiline patterns (operates line-by-line); non-matching lines
     Basis:      RAW (regex on raw file text, line-by-line)
     shared_ctx: none (stateless, reads only file_ctx.raw)
     Configured pattern: ^\s*print\s*(
     redact: False

     Worked example (tests/test_matchers/test_regex.py:TestRegexMatcherLineMatches.test_print_call_flagged):
         input:  print('hi')
         match:  line=1, column=1, matched_value="print("
```

**Reflection logic** (in new `enforcer/explain.py`):

- Load config via existing `load_config()`.
- Find rule by id in `RULES` (error if not found, list close matches).
- For each matcher in `rule.matchers`:
  - Class name (`type(matcher).__name__`).
  - Class docstring via `inspect.getdoc(matcher)`, parsed into the four labeled sections.
  - Configured parameters (non-default dataclass fields, via `dataclasses.fields(matcher)`).
  - Paired test path: `tests/test_matchers/test_{snake_case_class_name}.py` (e.g. `RegexMatcher` → `test_regex_matcher.py`; falling back to `test_regex.py` if not found — list both candidates).
  - Worked example: parse the test file AST (tree-sitter, already available), find the first test class + first test method, render its source as a 4-line snippet (input → match assertion). If parse fails, link the path and skip the snippet.

**JSON format** mirrors the structure; agent consumers (MCP server, CI commenter) use this for structured fix hints.

**MCP integration:** the existing `mcp_server.py` exposes rule metadata. Add an `explain_rule(rule_id)` tool that returns the same JSON. Agent at commit time can call it before fixing.

### Part 4 — Docs generator enhancement

`enforcer/docs.py` `render_rules_doc` already produces `CONVENTIONS.md`. Extend `_render_rule_doc` to append, after the existing `**Fix:**` / `**Why:**` blocks, a `**Matchers:**` block:

- For each matcher: class name + `What:` line (first section of class docstring).
- Path to paired test file (rendered as relative link in markdown).

No `examples` field, no inline code dumps — the docs link to tests, which are the source of truth.

### Part 5 — Self-enforcement rules for test coverage

Two new ERROR rules in `enforcer_config.py`, both `diff_only=True` so they fire only on changed matchers:

**`matcher-test-positive-negative`** — flags a matcher test file missing positive or negative coverage. Logic:
- Triggered when a matcher in `enforcer/matchers/*.py` is changed.
- Locates paired test file via existing `PairedFileMatcher` convention (`tests/test_matchers/test_{stem}*.py`).
- Parses the test file AST (tree-sitter Python).
- Positive: ≥1 test method whose name matches `test_*(fail|flags|violation)` OR whose body contains `assert` (not `assert not`) on a match-list truthiness/length. Parameterized: the method must carry `@pytest.mark.parametrize` with ≥3 cases (count decorator args or the `parametrize` arg list length).
- Negative: ≥1 test method whose name matches `test_*(success|clean|valid|passes)` OR whose body contains `assert not` / `assert len(...) == 0` on the match list. Same parameterization floor (≥3).
- Violation message names which side is missing and the parameterization shortfall.

**Implementation note:** detecting `assert` vs `assert not` reliably via AST: walk method body, find `assert` statements, inspect the test expression. `assert not X` or `assert len(X) == 0` = negative; `assert X` or `assert len(X) >= 1` = positive. Method-name heuristic is a fallback signal when AST inspection is ambiguous — flag if neither heuristic confirms coverage.

This matcher is itself a new matcher — `TestCoverageMatcher` — and ships with its own positive/negative parameterized tests per the convention it enforces.

## Architecture

New file: `enforcer/explain.py`

```
enforcer/explain.py
  load_rule_for_explain(config_path, rule_id) -> Rule | None
  render_matcher_explainer(matcher) -> MatcherExplainer  # dataclass
  render_rule_explainer(rule, config) -> str  # text
  render_rule_explainer_json(rule, config) -> dict
  _parse_docstring_sections(doc) -> dict[str, str]  # What/Ignores/Basis/shared_ctx
  _find_paired_test(matcher_class_name, workspace) -> Path | None
  _extract_worked_example(test_path, matcher_class_name) -> WorkedExample | None
```

Depends on: `enforcer.config.load_config`, `enforcer.types`, stdlib `inspect`, `dataclasses`, `pathlib`, existing tree-sitter parser for test-file AST extraction.

New CLI subcommand in `enforcer/cli.py`:

```python
@cli.command()
@click.argument("rule_id")
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]))
def explain(rule_id, config_path, fmt):
    """Explain what a rule matches, what it ignores, and show a worked example."""
```

## Testing

Paired test files:

**`tests/test_explain.py`** — covers:
- Happy path: `explain` finds rule, renders matcher docstrings, locates paired test.
- Missing rule id: lists close matches (Levenshtein on rule ids).
- Matcher with malformed docstring (missing `What:`): renders available sections, notes the gap.
- Paired test not found: renders matcher detail, skips worked example.
- `--format json`: structure matches text.
- Combinator-based rules (e.g. `AllOf(...)` inside `matchers`): recurses into combinator's `.matchers`.
- Worked example extraction: tree-sitter parse of a real test file returns the expected snippet.

**`tests/test_matchers/test_test_coverage.py`** — covers `TestCoverageMatcher` per the convention it enforces:
- Positive (flags): ≥3 cases — test file missing positive method, missing negative method, parameterization with <3 cases.
- Negative (clean): ≥3 cases — test file with both sides parameterized ≥3, file with extra scenarios beyond minimum, file using `assert not` variant naming.

Self-enforcement: existing `core-test-paired` rule flags `explain.py` as needing `tests/test_explain.py`; `matcher-test-paired` flags `test_coverage.py` as needing `tests/test_matchers/test_test_coverage.py`.

## Migration

- Retrofits matcher class docstrings to the four-section convention (20 existing matchers).
- Retrofits existing matcher test files to positive/negative parameterized convention (≥3 cases each side). Done as files are touched (diff_only); bulk retrofit optional.
- No `enforcer_config.py` changes required for docstring convention.
- New self-enforcement rules added to `enforcer_config.py`: `matcher-docstring-structured`, `matcher-test-positive-negative`.
- New matcher module: `enforcer/matchers/test_coverage.py` (`TestCoverageMatcher`) + paired tests.
- No `Rule` dataclass changes.

## Open Questions

1. **Worked example rendering depth.** Snippet of 4 lines (input + assertion) is enough for an agent; a human may want the full test method. Proposal: text format shows 4 lines + file:line link; `--verbose` (future) shows full method. Out of scope for this spec — ship the 4-line version, revisit if requested.

2. **`matcher-docstring-structured` enforcement strictness.** Requiring `What:` is the floor. Should it also require `Basis:`? Proposal: yes — `Basis:` tells the reader whether this is a regex or AST matcher in one word, high signal. Enforce both `What:` and `Basis:`.

3. **Test file path discovery.** `RegexMatcher` → `test_regex.py` (current) vs `test_regex_matcher.py` (convention consistent with `test_<name>.py` where `<name>` is snake_case of class). Proposal: accept both, prefer the longer form in new tests, don't rename existing test files (renames break git history for no clarity gain).

4. **`TestCoverageMatcher` detection signal.** AST inspect of `assert` vs `assert not` is the primary signal; method-name heuristic (`test_*_fail` / `test_*_success`) is fallback. If both signals are present but disagree (e.g. method named `test_foo_success` containing a positive `assert`), which wins? Proposal: AST wins — names drift, assertions are ground truth. Flag the naming as a separate advisory if they disagree (severity INFO).
