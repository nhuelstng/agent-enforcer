from enforcer import Match
from enforcer.predicates import StringMatchesPredicate, StringNotMatchesPredicate

def test_string_matches():
    m = Match(file="x", line=1, matched_value="#aabbcc")
    assert StringMatchesPredicate(r"^#").test(m)
    assert StringMatchesPredicate(r"^#ff").test(m) is False

def test_string_not_matches():
    m = Match(file="x", line=1, matched_value="var(--color)")
    assert StringNotMatchesPredicate(r"^#").test(m)
    assert StringNotMatchesPredicate(r"^var").test(m) is False

def test_string_matches_partial():
    m = Match(file="x", line=1, matched_value="color: #fff;")
    assert StringMatchesPredicate(r"#fff").test(m)
