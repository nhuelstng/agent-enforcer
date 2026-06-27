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

    def test(self, match: Match) -> bool:
        return _OPS[self.op](len(match.matched_value), self.value)
