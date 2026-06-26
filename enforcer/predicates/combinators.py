from __future__ import annotations
from dataclasses import dataclass

@dataclass
class All:
    predicates: list

    def test(self, match) -> bool:
        return all(p.test(match) for p in self.predicates)

@dataclass
class Any:
    predicates: list

    def test(self, match) -> bool:
        return any(p.test(match) for p in self.predicates)

@dataclass
class NotP:
    predicate: object

    def test(self, match) -> bool:
        return not self.predicate.test(match)
