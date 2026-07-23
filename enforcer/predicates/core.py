"""The predicate contract and the one comparison-operator table they share.

Every predicate filters a Match to a keep/drop bool via test(). Threshold predicates
(numeric value, string length) share COMPARISONS so their supported operators can't
drift apart — previously each kept its own table and they disagreed on '!='."""
from __future__ import annotations
from typing import Callable, Protocol, runtime_checkable
from enforcer.types import Match

# ponytail: the comparison operators every threshold predicate supports.
COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@runtime_checkable
class Predicate(Protocol):
    """Filters a Match to a keep/drop decision — the seam Rule.check applies after matching.

    Matchers produce candidate matches; a rule's predicates then each return True to keep
    a match or False to drop it. Value comparisons, regex tests, AST inspections, and
    combinators all present this one method."""
    def test(self, match: Match) -> bool:
        """Return True to keep the match, False to drop it."""
        ...
