from enforcer.docs import render_rules_markdown
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher


def test_render_empty_rules():
    md = render_rules_markdown([])
    assert "# Conventions" in md
    assert "No rules configured." in md


def test_render_single_rule():
    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts", "**/*.scss"],
            exclude_globs=["**/*.spec.ts"],
            message="Raw hex color '{matched_value}' found. Use var(--color-*).",
            fix_instruction="Replace with var(--color-*) from colors.scss.",
        ),
    ]
    md = render_rules_markdown(rules)
    assert "# Conventions" in md
    assert "## no-raw-hex" in md
    assert "ERROR" in md
    assert "**/*.ts" in md
    assert "**/*.spec.ts" in md
    assert "var(--color-*)" in md


def test_render_multiple_rules_sorted():
    rules = [
        Rule(id="z-rule", severity=Severity.INFO, matchers=[], file_globs=["**/*.ts"]),
        Rule(id="a-rule", severity=Severity.ERROR, matchers=[], file_globs=["**/*.ts"]),
    ]
    md = render_rules_markdown(rules)
    lines = md.split("\n")
    a_idx = next(i for i, l in enumerate(lines) if "a-rule" in l)
    z_idx = next(i for i, l in enumerate(lines) if "z-rule" in l)
    assert a_idx < z_idx


def test_render_includes_llm_consequence():
    from enforcer import LLMConsequence
    rules = [
        Rule(
            id="nl-check",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            llm_consequence=LLMConsequence(
                provider="test", model="gpt-4",
                prompt="Is this function focused and short?",
            ),
        ),
    ]
    md = render_rules_markdown(rules)
    assert "focused and short" in md
    assert "gpt-4" in md


def test_render_includes_read_targets():
    rules = [
        Rule(
            id="cross-file",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["**/*.ts"],
            read_targets=["**/colors.scss"],
        ),
    ]
    md = render_rules_markdown(rules)
    assert "colors.scss" in md


import re
import pytest
from enforcer.docs import render_rules_doc


def test_render_doc_empty_rules():
    md = render_rules_doc([])
    assert "# Conventions" in md
    assert "No rules configured." in md


def test_render_doc_single_rule_with_rationale():
    rules = [
        Rule(
            id="no-print",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"^\s*print\s*\(")],
            file_globs=["enforcer/**/*.py"],
            message="print() found in library code at {file}:{line}.",
            fix_instruction="Replace print() with sys.stderr.write(...).",
            rationale="print() writes to stdout, which is reserved for machine-readable output.",
        ),
    ]
    md = render_rules_doc(rules)
    assert "# Conventions" in md
    assert "## ERROR" in md
    assert "### no-print" in md
    assert "**Why:**" in md
    assert "machine-readable output" in md
    assert "**Applies to:**" in md
    assert "enforcer/**/*.py" in md
    assert "**Fix:**" in md
    assert "sys.stderr.write" in md


def test_render_doc_rule_without_rationale():
    rules = [
        Rule(
            id="no-print",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["enforcer/**/*.py"],
            message="print() found.",
            fix_instruction="Replace print().",
        ),
    ]
    md = render_rules_doc(rules)
    assert "### no-print" in md
    assert "**Why:**" not in md


def test_render_doc_whitespace_only_rationale_omitted():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="msg",
            rationale="   ",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Why:**" not in md


def test_render_doc_callable_message_guard():
    rules = [
        Rule(
            id="dyn",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message=lambda m: f"Dynamic at {m.line}",
        ),
    ]
    md = render_rules_doc(rules)
    assert "(dynamic message)" in md


def test_render_doc_llm_consequence():
    from enforcer import LLMConsequence
    rules = [
        Rule(
            id="llm-rule",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["*.py"],
            llm_consequence=LLMConsequence(
                provider="test", model="gpt-4",
                prompt="Is this function focused?",
            ),
        ),
    ]
    md = render_rules_doc(rules)
    assert "**LLM check:**" in md
    assert "Is this function focused?" in md
    assert "gpt-4" in md


def test_render_doc_diff_only_note():
    rules = [
        Rule(
            id="diff-rule",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="msg",
            diff_only=True,
        ),
    ]
    md = render_rules_doc(rules)
    assert "changed lines only" in md


def test_render_doc_severity_grouping_order():
    rules = [
        Rule(id="z-info", severity=Severity.INFO, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="a-error", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="m-warn", severity=Severity.WARN, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    lines = md.split("\n")
    err_idx = next(i for i, l in enumerate(lines) if "## ERROR" in l)
    warn_idx = next(i for i, l in enumerate(lines) if "## WARN" in l)
    info_idx = next(i for i, l in enumerate(lines) if "## INFO" in l)
    assert err_idx < warn_idx < info_idx


def test_render_doc_sorted_within_group():
    rules = [
        Rule(id="z-rule", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="a-rule", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    lines = md.split("\n")
    a_idx = next(i for i, l in enumerate(lines) if "### a-rule" in l)
    z_idx = next(i for i, l in enumerate(lines) if "### z-rule" in l)
    assert a_idx < z_idx


def test_render_doc_determinism():
    rules = [
        Rule(id="b", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m", rationale="why"),
        Rule(id="a", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m", rationale="why"),
    ]
    md1 = render_rules_doc(rules)
    md2 = render_rules_doc(rules)
    assert md1 == md2


def test_render_doc_placeholder_stripping():
    rules = [
        Rule(
            id="snake",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            message="Function '{matched_value}' at {file}:{line} must be snake_case",
        ),
    ]
    md = render_rules_doc(rules)
    assert "{matched_value}" not in md
    assert "{file}" not in md
    assert "{line}" not in md
    assert "Function" in md
    assert "snake_case" in md


def test_render_doc_metadata_suffix():
    from enforcer import RuleType
    rules = [
        Rule(
            id="branch-naming",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*"],
            rule_type=RuleType.METADATA,
            message="Branch doesn't match pattern.",
        ),
    ]
    md = render_rules_doc(rules)
    assert "metadata rule, checked once per run" in md


def test_render_doc_excludes_line():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            exclude_globs=["**/test*"],
            message="m",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Excludes:**" in md
    assert "**/test*" in md


def test_render_doc_read_targets_line():
    rules = [
        Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["*.py"],
            read_targets=["**/colors.scss"],
            message="m",
        ),
    ]
    md = render_rules_doc(rules)
    assert "**Read targets:**" in md
    assert "colors.scss" in md


def test_render_doc_rule_count_in_header():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        Rule(id="b", severity=Severity.WARN, matchers=[], file_globs=["*.py"], message="m"),
    ]
    md = render_rules_doc(rules)
    assert "2 rules configured" in md


class TestRenderDocMatchersBlock:
    """renders a Matchers block with class name and What: line."""

    @pytest.mark.parametrize("present_substring", [
        "**Matchers:**",
        "RegexMatcher",
    ])
    def test_matchers_block_present(self, present_substring):
        rules = [
            Rule(
                id="no-print",
                severity=Severity.ERROR,
                matchers=[RegexMatcher(r"^\s*print\s*\(")],
                file_globs=["*.py"],
                message="m",
            ),
        ]
        md = render_rules_doc(rules)
        assert present_substring in md

    def test_matchers_block_omitted_when_no_matchers(self):
        rules = [
            Rule(id="empty", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="m"),
        ]
        md = render_rules_doc(rules)
        assert "**Matchers:**" not in md

    def test_matchers_block_links_paired_test(self):
        rules = [
            Rule(
                id="no-print",
                severity=Severity.ERROR,
                matchers=[RegexMatcher(r"^\s*print\s*\(")],
                file_globs=["*.py"],
                message="m",
            ),
        ]
        md = render_rules_doc(rules)
        assert "test_regex" in md  # paired test path referenced
