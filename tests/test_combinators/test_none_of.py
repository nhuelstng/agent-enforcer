from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import NoneOf

def test_none_of_all_absent():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    matches = m.find(ctx)
    assert len(matches) == 1

def test_none_of_one_present():
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    m = NoneOf([RegexMatcher(r"#fff"), RegexMatcher(r"\bdebugger\b")])
    assert m.find(ctx) == []


import pytest


@pytest.mark.parametrize("raw", ["\n", "z\n", "qqq\n"])
def test_none_of_flags_violation(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = NoneOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert result


@pytest.mark.parametrize("raw", ["a\n", "a b\n", "aaa\n"])
def test_none_of_passes_clean(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = NoneOf([RegexMatcher(r"a"), RegexMatcher(r"\bdebugger\b")]).find(ctx)
    assert not result
