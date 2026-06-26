import pytest
from enforcer import Severity, FileContext
from enforcer.runner import RuleRunner
from enforcer.matchers import RegexMatcher, LineCountMatcher
from enforcer.rule import Rule

def test_runner_collects_all_matches():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
             file_globs=["**/*.ts"], message="Found {matched_value}"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff #000 #aaa")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 3

def test_runner_multiple_rules():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="hex"),
        Rule(id="lines", severity=Severity.WARN,
             matchers=[LineCountMatcher(max_lines=2)],
             file_globs=["**/*.ts"], message="too long"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff\nline2\nline3\n")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 2
    rule_ids = {m.rule_id for m in matches}
    assert rule_ids == {"hex", "lines"}

def test_runner_respects_file_globs():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.scss"], message="hex"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.ts", raw="#fff")
    matches = runner.run_rules_for_file(ctx, {})
    assert matches == []

def test_runner_respects_exclude_globs():
    rules = [
        Rule(id="hex", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"],
             exclude_globs=["**/*.spec.ts"],
             message="hex"),
    ]
    runner = RuleRunner(rules, workspace=".")
    ctx = FileContext(path="x.spec.ts", raw="#fff")
    matches = runner.run_rules_for_file(ctx, {})
    assert matches == []

def test_runner_no_llm():
    from enforcer import LLMConsequence
    rules = [
        Rule(id="lines", severity=Severity.WARN,
             matchers=[LineCountMatcher(max_lines=2)],
             file_globs=["**/*.ts"], message="x",
             llm_consequence=LLMConsequence(provider="p", model="m", prompt="x")),
    ]
    runner = RuleRunner(rules, workspace=".", no_llm=True)
    ctx = FileContext(path="x.ts", raw="line1\nline2\nline3\n")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 1
    assert matches[0].llm_response == ""

def test_runner_filter_by_severity():
    rules = [
        Rule(id="warn", severity=Severity.WARN,
             matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="w"),
        Rule(id="err", severity=Severity.ERROR,
             matchers=[RegexMatcher(r"#000")],
             file_globs=["**/*.ts"], message="e"),
    ]
    runner = RuleRunner(rules, workspace=".", min_severity=Severity.ERROR)
    ctx = FileContext(path="x.ts", raw="#fff #000")
    matches = runner.run_rules_for_file(ctx, {})
    assert len(matches) == 1
    assert matches[0].rule_id == "err"
