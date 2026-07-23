"""IntPredicate: compares an integer value against a threshold using an operator (lt, le, eq, ne, ge, gt)."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match
from enforcer.predicates.core import COMPARISONS, Predicate

@dataclass
class IntPredicate(Predicate):
    """Predicate for integer comparisons. Tests a value against a threshold with the given operator."""
    op: str
    value: int

    def __post_init__(self):
        if self.op not in COMPARISONS:
            raise ValueError(f"Invalid op: {self.op!r}. Valid: {sorted(COMPARISONS)}")

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        try:
            val = int(match.matched_value)
        except (ValueError, TypeError):
            return False
        return COMPARISONS[self.op](val, self.value)
