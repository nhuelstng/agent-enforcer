"""StringLengthPredicate: checks string length against a predicate."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match
from enforcer.predicates.core import COMPARISONS, Predicate

@dataclass
class StringLengthPredicate(Predicate):
    """Tests whether the length of a string value meets a threshold condition."""
    op: str
    value: int

    def __post_init__(self):
        if self.op not in COMPARISONS:
            raise ValueError(f"Invalid op: {self.op!r}. Valid: {sorted(COMPARISONS)}")

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        try:
            return COMPARISONS[self.op](len(match.matched_value), self.value)
        except (TypeError, AttributeError):
            return False
