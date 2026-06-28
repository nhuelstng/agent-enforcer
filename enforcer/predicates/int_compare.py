"""IntPredicate: compares an integer value against a threshold using an operator (lt, le, eq, ne, ge, gt)."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

@dataclass
class IntPredicate:
    """Predicate for integer comparisons. Tests a value against a threshold with the given operator."""
    op: str
    value: int

    def __post_init__(self):
        if self.op not in _OPS:
            raise ValueError(f"Invalid op: {self.op!r}. Valid: {sorted(_OPS)}")

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        try:
            val = int(match.matched_value)
        except (ValueError, TypeError):
            return False
        return _OPS[self.op](val, self.value)
