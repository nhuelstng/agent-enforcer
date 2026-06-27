"""StringMatchesPredicate and StringNotMatchesPredicate: regex match testing on string values."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match

@dataclass
class StringMatchesPredicate:
    """Tests whether a string value matches a regex pattern."""
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return bool(re.search(self.pattern, match.matched_value))

@dataclass
class StringNotMatchesPredicate:
    """Tests whether a string value does NOT match a regex pattern."""
    pattern: str | Pattern

    def test(self, match: Match) -> bool:
        return not bool(re.search(self.pattern, match.matched_value))
