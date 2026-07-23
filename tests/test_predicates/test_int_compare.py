from enforcer import Match
from enforcer.predicates import IntPredicate

def test_int_greater_than():
    m = Match(file="x", line=1, matched_value="42")
    assert IntPredicate(op=">", value=10).test(m) is True
    assert IntPredicate(op=">", value=50).test(m) is False

def test_int_all_operators():
    m = Match(file="x", line=1, matched_value="5")
    assert IntPredicate(op=">", value=4).test(m)
    assert IntPredicate(op="<", value=6).test(m)
    assert IntPredicate(op=">=", value=5).test(m)
    assert IntPredicate(op="<=", value=5).test(m)
    assert IntPredicate(op="==", value=5).test(m)
    assert IntPredicate(op="!=", value=6).test(m)

def test_int_non_numeric():
    m = Match(file="x", line=1, matched_value="not_a_number")
    assert IntPredicate(op=">", value=10).test(m) is False

def test_int_negative():
    m = Match(file="x", line=1, matched_value="-5")
    assert IntPredicate(op="<", value=0).test(m) is True


import pytest


@pytest.mark.parametrize("value", ["6", "7", "10"])
def test_int_gt_passes(value):
    assert IntPredicate(op=">", value=5).test(Match(file="x", line=1, matched_value=value)) is True


@pytest.mark.parametrize("value", ["1", "2", "5"])
def test_int_gt_fails(value):
    assert not IntPredicate(op=">", value=5).test(Match(file="x", line=1, matched_value=value))
