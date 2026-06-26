from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AllOf

def test_all_of_all_match():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_all_of_one_missing():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = AllOf([
        RegexMatcher(r"\bconst\b"),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert matches == []

def test_all_of_empty():
    ctx = FileContext(path="x.ts", raw="")
    m = AllOf([RegexMatcher(r"test")])
    assert m.find(ctx) == []

def test_all_of_single_matcher():
    ctx = FileContext(path="x.ts", raw="#fff")
    m = AllOf([RegexMatcher(r"#fff")])
    matches = m.find(ctx)
    assert len(matches) == 1
