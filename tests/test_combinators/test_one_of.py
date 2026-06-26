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
