"""StringMatchesPredicate and StringNotMatchesPredicate: regex match testing on string values."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match
from enforcer.predicates.core import Predicate

@dataclass
class StringMatchesPredicate(Predicate):
    """Tests whether a string value matches a regex pattern."""
    pattern: str | Pattern

    def __post_init__(self):
        if isinstance(self.pattern, str):
            self._compiled = re.compile(self.pattern)
        else:
            self._compiled = self.pattern

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        return bool(self._compiled.search(match.matched_value))

@dataclass
class StringNotMatchesPredicate(Predicate):
    """Tests whether a string value does NOT match a regex pattern."""
    pattern: str | Pattern

    def __post_init__(self):
        if isinstance(self.pattern, str):
            self._compiled = re.compile(self.pattern)
        else:
            self._compiled = self.pattern

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        return not bool(self._compiled.search(match.matched_value))
