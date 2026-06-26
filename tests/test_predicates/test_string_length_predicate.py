from enforcer import Match
from enforcer.predicates import StringLengthPredicate

def test_string_length():
    m = Match(file="x", line=1, matched_value="hello")
    assert StringLengthPredicate(op=">", value=3).test(m)
    assert StringLengthPredicate(op=">", value=5).test(m) is False
    assert StringLengthPredicate(op="==", value=5).test(m)

def test_string_length_empty():
    m = Match(file="x", line=1, matched_value="")
    assert StringLengthPredicate(op="==", value=0).test(m)

def test_string_length_ge():
    m = Match(file="x", line=1, matched_value="ab")
    assert StringLengthPredicate(op=">=", value=2).test(m)
    assert StringLengthPredicate(op=">=", value=3).test(m) is False
