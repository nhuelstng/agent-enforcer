from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import AllOf, AnyOf, OneOf, Not, NoneOf

def test_nested_anyof_inside_allof():
    ctx = FileContext(path="x.ts", raw="console.log('x'); #fff;")
    m = AllOf([
        AnyOf([RegexMatcher(r"\bconsole\.log\b"), RegexMatcher(r"\bdebugger\b")]),
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_nested_not_inside_allof():
    ctx = FileContext(path="x.ts", raw="const x = #fff;")
    m = AllOf([
        RegexMatcher(r"#[0-9a-fA-F]{3,6}\b"),
        Not(RegexMatcher(r"\bdebugger\b")),
    ])
    matches = m.find(ctx)
    assert len(matches) == 2

def test_deeply_nested():
    ctx = FileContext(path="x.ts", raw="console.log(#fff);")
    m = AllOf([
        AnyOf([
            Not(RegexMatcher(r"\bdebugger\b")),
            RegexMatcher(r"\bconsole\.log\b"),
        ]),
        Not(NoneOf([RegexMatcher(r"#fff")])),
    ])
    matches = m.find(ctx)
    assert len(matches) >= 2
