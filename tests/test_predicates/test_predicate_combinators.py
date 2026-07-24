from enforcer import Match
from enforcer.predicates import IntPredicate, All, Any, NotP

def test_all_predicates():
    m = Match(file="x", line=1, matched_value="42")
    p = All([IntPredicate(op=">", value=10), IntPredicate(op="<", value=100)])
    assert p.test(m)

def test_all_predicates_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = All([IntPredicate(op=">", value=10), IntPredicate(op="<", value=40)])
    assert not p.test(m)

def test_any_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = Any([IntPredicate(op=">", value=50), IntPredicate(op="<", value=50)])
    assert p.test(m)

def test_any_predicate_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = Any([IntPredicate(op=">", value=50), IntPredicate(op=">", value=50)])
    assert not p.test(m)

def test_not_predicate():
    m = Match(file="x", line=1, matched_value="42")
    p = NotP(IntPredicate(op=">", value=50))
    assert p.test(m)

def test_not_predicate_fails():
    m = Match(file="x", line=1, matched_value="42")
    p = NotP(IntPredicate(op="<", value=50))
    assert not p.test(m)


import pytest


@pytest.mark.parametrize("value", ["6", "7", "10"])
def test_combinator_passes(value):
    p = All([IntPredicate(op=">", value=5), Any([IntPredicate(op="<", value=100)])])
    assert p.test(Match(file="x", line=1, matched_value=value)) is True


@pytest.mark.parametrize("value", ["1", "2", "5"])
def test_combinator_fails(value):
    p = All([IntPredicate(op=">", value=5), NotP(IntPredicate(op="==", value=99))])
    assert not p.test(Match(file="x", line=1, matched_value=value))
