"""Predicate implementations: filter match results by numeric or string conditions."""
from enforcer.predicates.int_compare import IntPredicate
from enforcer.predicates.string_length import StringLengthPredicate
from enforcer.predicates.string_matches import StringMatchesPredicate, StringNotMatchesPredicate
from enforcer.predicates.combinators import All, Any, NotP

__all__ = [
    "IntPredicate",
    "StringLengthPredicate",
    "StringMatchesPredicate",
    "StringNotMatchesPredicate",
    "All",
    "Any",
    "NotP",
]
