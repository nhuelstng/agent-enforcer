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
