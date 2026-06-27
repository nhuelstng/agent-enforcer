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

    def test(self, match: Match) -> bool:
        try:
            val = int(match.matched_value)
        except (ValueError, TypeError):
            return False
        return _OPS[self.op](val, self.value)
