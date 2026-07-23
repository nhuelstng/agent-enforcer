from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AnyOf

def test_any_of_one_matches():
    ctx = FileContext(path="x.ts", raw="const x = 1;")
    m = AnyOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        RegexMatcher(r"\bconst\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "const"

def test_any_of_all_match():
    ctx = FileContext(path="x.ts", raw="const #fff;")
    m = AnyOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_any_of_none_match():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AnyOf([
        RegexMatcher(r"#fff"),
        RegexMatcher(r"\bconst\b"),
    ])
    assert m.find(ctx) == []


import pytest


@pytest.mark.parametrize("raw", ["a\n", "a b\n", "aaa\n"])
def test_any_of_flags_violation(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AnyOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert result


@pytest.mark.parametrize("raw", ["\n", "z\n", "qqq\n"])
def test_any_of_passes_clean(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AnyOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert not result
