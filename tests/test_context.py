import pytest
from enforcer import Needs, Severity
from enforcer.context import FileContextBuilder
from enforcer.matchers import RegexMatcher, LineCountMatcher
from enforcer.rule import Rule

def test_builder_provides_raw():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    ctx = builder.build("tests/fixtures/sample.ts")
    assert ctx.raw is not None
    assert ctx.path == "tests/fixtures/sample.ts"

def test_builder_aggregates_needs():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[LineCountMatcher(max_lines=10)],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.ts", rules)
    assert Needs.RAW in needs
