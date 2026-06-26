from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match

@dataclass
class StringMatchesPredicate:
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return bool(re.search(self.pattern, match.matched_value))

@dataclass
class StringNotMatchesPredicate:
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return not bool(re.search(self.pattern, match.matched_value))
