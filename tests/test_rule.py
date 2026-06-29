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

def test_rule_rationale_default_empty():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
    )
    assert rule.rationale == ""


def test_rule_rationale_set():
    rule = Rule(
        id="test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        rationale="Hex colors break theming.",
    )
    assert rule.rationale == "Hex colors break theming."
