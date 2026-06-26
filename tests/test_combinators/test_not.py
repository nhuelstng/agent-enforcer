from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import Not

def test_not_matcher_absent():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = Not(RegexMatcher(r"#fff"), message_on_absence="No hex found")
    matches = m.find(ctx)
    assert len(matches) == 1
    assert "No hex found" in matches[0].message

def test_not_matcher_present():
    ctx = FileContext(path="x.ts", raw="color: #fff;")
    m = Not(RegexMatcher(r"#fff"))
    assert m.find(ctx) == []

def test_not_default_message():
    ctx = FileContext(path="x.ts", raw="let x = 1;")
    m = Not(RegexMatcher(r"#fff"))
    matches = m.find(ctx)
    assert len(matches) == 1
