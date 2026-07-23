"""The one place that knows the shape of a matcher/combinator tree.

Four call sites previously re-derived "how do I descend a combinator" by probing
`.matchers`/`.matcher` with hasattr: context (collect Needs), runner (collect
finalizers), check_runner (detect import-graph consumers), explain (flatten for
rendering). They now share `_children`, so the tree shape is defined once."""
from __future__ import annotations
from typing import Iterator


def _children(matcher) -> list:
    """Return a combinator's child matchers.

    A `matchers` list (AllOf/AnyOf/OneOf/NoneOf) or a single `matcher` (Not/StatusGate);
    a leaf matcher has neither and yields no children."""
    children = getattr(matcher, "matchers", None)
    if isinstance(children, list):
        return children
    child = getattr(matcher, "matcher", None)
    return [child] if child is not None else []


def is_combinator(matcher) -> bool:
    """True if the matcher composes children — it exposes a child slot and a find().

    The child slot is a `matchers` list or a single `matcher`; leaf matchers have neither.
    This is the one predicate that decides "combinator vs leaf" for the whole codebase."""
    has_slot = isinstance(getattr(matcher, "matchers", None), list) or getattr(matcher, "matcher", None) is not None
    return has_slot and callable(getattr(matcher, "find", None))


def iter_matchers(matchers: list) -> Iterator:
    """Yield every matcher and combinator in the trees, depth-first (order-insensitive).

    Combinators are yielded alongside their descendants, so capability filters
    (finalizers, import-graph consumers, declared Needs) see every node."""
    stack: list = list(matchers)
    while stack:
        m = stack.pop()
        yield m
        stack.extend(_children(m))


def walk_with_depth(matchers: list) -> list[tuple[int, object]]:
    """Flatten the trees to (depth, matcher) pairs, preserving sibling order.

    For rendering, where nesting depth and left-to-right order are both significant.
    Iterative DFS with reverse-push to keep siblings in declaration order on pop."""
    flat: list[tuple[int, object]] = []
    stack: list[tuple[int, object]] = [(0, m) for m in reversed(matchers)]
    while stack:
        depth, m = stack.pop()
        flat.append((depth, m))
        for child in reversed(_children(m)):
            stack.append((depth + 1, child))
    return flat
