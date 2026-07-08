"""CSS tree-sitter AST navigation helpers: declaration / property / value walking.

Shared by the CSS matchers so each does not re-implement tree-sitter-css
traversal. Node shapes (verified against tree-sitter-css):

    declaration -> property_name, ':', <value nodes...>, ';'
    value nodes: color_value (#hex), integer_value/float_value (+ unit child),
                 call_expression (-> function_name, arguments), plain_value,
                 string_value.
"""
from __future__ import annotations
from typing import Iterator

from enforcer.parsers.ast_utils import node_text


def iter_declarations(root) -> Iterator:
    """Yield every `declaration` node under `root` in document order (deep-safe DFS)."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "declaration":
            yield node
        stack.extend(reversed(node.children))


def property_name(decl) -> str:
    """Return a declaration's property name (e.g. 'color', '--token'), or '' if absent."""
    for child in decl.children:
        if child.type == "property_name":
            return node_text(child)
    return ""


def value_nodes(decl) -> list:
    """Return a declaration's value nodes — everything after the ':' separator."""
    out: list = []
    seen_colon = False
    for child in decl.children:
        if child.type == ":":
            seen_colon = True
        elif child.type in (";", "property_name"):
            continue
        elif seen_colon:
            out.append(child)
    return out


def descendants(node) -> Iterator:
    """Yield `node` and all its descendants in document order (deep-safe DFS)."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))
