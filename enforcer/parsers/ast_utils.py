"""Shared AST utilities: iterative walker + node-type constants for Python/TS."""
from __future__ import annotations
from typing import Iterator

FUNC_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
}

DECL_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "class_definition",
    "class_declaration",
    "variable_declaration",
}

IMPORT_NODE_TYPES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
}


def walk_ast(root) -> Iterator:
    """Iterative DFS. Yields root then all descendants. Avoids RecursionError on deep ASTs."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def find_functions(root) -> list:
    """Return all function/method nodes in the AST (iterative DFS)."""
    return [n for n in walk_ast(root) if n.type in FUNC_NODE_TYPES]


def node_text(node) -> str:
    """Decode node.text: bytes→str, str→str."""
    raw = node.text
    return raw.decode() if isinstance(raw, bytes) else str(raw)
