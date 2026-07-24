from dataclasses import dataclass, field
from enforcer import Needs, Severity, FileContext, Match
from enforcer.context import FileContextBuilder
from enforcer.matchers import ImportMatcher
from enforcer.combinators import AllOf, AnyOf, OneOf, Not, NoneOf
from enforcer.rule import Rule


def test_needs_for_file_with_allof_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[AllOf([ImportMatcher(["x"], needs=Needs.AST_PY)])],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_needs_for_file_with_anyof_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[AnyOf([ImportMatcher(["x"], needs=Needs.AST_PY)])],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_needs_for_file_with_oneof_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[OneOf([ImportMatcher(["x"], needs=Needs.AST_PY)])],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_needs_for_file_with_not_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[Not(ImportMatcher(["x"], needs=Needs.AST_PY))],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_needs_for_file_with_noneof_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[NoneOf([ImportMatcher(["x"], needs=Needs.AST_PY)])],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_needs_for_file_deeply_nested_combinator():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[AllOf([AnyOf([Not(ImportMatcher(["x"], needs=Needs.AST_PY))])])],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs


def test_combinators_declare_needs_attribute():
    """AGENTS.md matcher contract: every matcher (incl. combinators) must declare a `needs` class attribute."""
    from enforcer.matchers import ImportMatcher
    inner = ImportMatcher(["x"], needs=Needs.AST_PY)
    assert hasattr(AllOf([inner]), "needs")
    assert hasattr(AnyOf([inner]), "needs")
    assert hasattr(OneOf([inner]), "needs")
    assert hasattr(Not(inner), "needs")
    assert hasattr(NoneOf([inner]), "needs")


def test_needs_for_file_combinator_and_plain_matcher():
    rules = [
        Rule(id="a", severity=Severity.ERROR,
             matchers=[
                 AllOf([ImportMatcher(["x"], needs=Needs.AST_PY)]),
                 ImportMatcher(["y"], needs=Needs.AST_TS),
             ],
             file_globs=["**/*.py"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.py", rules)
    assert Needs.AST_PY in needs
    assert Needs.AST_TS in needs


import pytest
from enforcer.matchers import RegexMatcher


@pytest.mark.parametrize("raw", ["a\n", "a b\n", "aaa\n"])
def test_needs_combinator_flags_violation(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AllOf([RegexMatcher(r"a")]).find(ctx)
    assert result


@pytest.mark.parametrize("raw", ["\n", "z\n", "qqq\n"])
def test_needs_combinator_passes_clean(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AllOf([RegexMatcher(r"a")]).find(ctx)
    assert not result
