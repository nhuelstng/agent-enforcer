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
