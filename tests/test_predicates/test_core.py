"""The predicate seam: one shared operator table + the Predicate Protocol."""
import pytest
from enforcer.types import Match
from enforcer.predicates.core import COMPARISONS, Predicate
from enforcer.predicates import (
    IntPredicate, StringLengthPredicate, StringMatchesPredicate,
    StringNotMatchesPredicate, All, Any, NotP,
)


def _m(value: str) -> Match:
    return Match(file="x", line=1, matched_value=value)


@pytest.mark.parametrize("op", [">", "<", ">=", "<=", "==", "!="])
def test_comparisons_table_supports_all_operators(op):
    """COMPARISONS is the single operator table — both threshold predicates accept every op."""
    assert op in COMPARISONS
    assert IntPredicate(op, 5).op in COMPARISONS


@pytest.mark.parametrize("op,val,keep", [
    (">", "6", True), ("!=", "3", True), ("==", "5", True),
])
def test_int_predicate_keeps_matching(op, val, keep):
    """IntPredicate keeps a match when the comparison against its threshold holds."""
    assert IntPredicate(op, 5).test(_m(val)) is keep


@pytest.mark.parametrize("op,val", [
    ("<", "9"), ("==", "1"), ("!=", "5"),
])
def test_int_predicate_drops_non_matching(op, val):
    """IntPredicate drops a match when the comparison fails (incl. '!=', once divergent)."""
    assert not IntPredicate(op, 5).test(_m(val))


@pytest.mark.parametrize("pred", [
    IntPredicate(">", 1), StringLengthPredicate(">", 1),
    StringMatchesPredicate("x"), StringNotMatchesPredicate("x"),
    All([]), Any([]), NotP(IntPredicate(">", 1)),
])
def test_all_predicates_satisfy_protocol(pred):
    """Every predicate — value, regex, and combinator — satisfies the Predicate Protocol."""
    assert isinstance(pred, Predicate)


def test_string_length_now_supports_ne():
    """StringLengthPredicate gained '!=' from the shared table (previously unsupported)."""
    assert StringLengthPredicate("!=", 3).test(_m("ab")) is True
    assert not StringLengthPredicate("!=", 2).test(_m("ab"))
