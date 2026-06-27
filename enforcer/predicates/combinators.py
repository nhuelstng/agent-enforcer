"""Predicate combinators: All (AND), Any (OR), NotP (NOT)."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class All:
    """All predicates must pass. Short-circuits on first failure."""
    predicates: list

    def test(self, match) -> bool:
        return all(p.test(match) for p in self.predicates)

@dataclass
class Any:
    """At least one predicate must pass."""
    predicates: list

    def test(self, match) -> bool:
        return any(p.test(match) for p in self.predicates)

@dataclass
class NotP:
    """Negates a predicate."""
    predicate: object

    def test(self, match) -> bool:
        return not self.predicate.test(match)
