"""StringLengthPredicate: checks string length against a predicate."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}

@dataclass
class StringLengthPredicate:
    """Tests whether the length of a string value meets a threshold condition."""
    op: str
    value: int

    def __post_init__(self):
        if self.op not in _OPS:
            raise ValueError(f"Invalid op: {self.op!r}. Valid: {sorted(_OPS)}")

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        try:
            return _OPS[self.op](len(match.matched_value), self.value)
        except (TypeError, AttributeError):
            return False
