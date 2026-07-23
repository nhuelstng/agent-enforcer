from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import OneOf

def test_one_of_exactly_one():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = OneOf([
        RegexMatcher(r"#fff"),
        RegexMatcher(r"\bconst\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_one_of_two_matchers_match():
    ctx = FileContext(path="x.ts", raw="const #fff;")
    m = OneOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    assert m.find(ctx) == []

def test_one_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = OneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bconst\b")])
    assert m.find(ctx) == []


import pytest


@pytest.mark.parametrize("raw", ["a\n", "a b\n", "aaa\n"])
def test_one_of_flags_violation(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = OneOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert result


@pytest.mark.parametrize("raw", ["\n", "z\n", "qqq\n"])
def test_one_of_passes_clean(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = OneOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert not result
