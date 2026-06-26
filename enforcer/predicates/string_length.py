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
    op: str
    value: int

    def test(self, match: Match) -> bool:
        return _OPS[self.op](len(match.matched_value), self.value)
