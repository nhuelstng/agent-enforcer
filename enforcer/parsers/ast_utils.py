"""Shared AST utilities: iterative walker + node-type constants for Python/TS."""
from __future__ import annotations
import re
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


def import_line_for(root, target_path: str) -> int:
    """Return the 1-based line of the import statement resolving to target_path, or 0.

    target_path is an on-disk path (e.g. 'pkg/b/api.py'); it is normalised to a
    dotted module and matched on a word boundary so 'pkg.b' does not mis-attribute
    to 'import pkg.billing'.
    """
    if root is None:
        return 0
    target_module = target_path.replace("/", ".").removesuffix(".__init__").removesuffix(".py")
    for node in walk_ast(root):
        if node.type not in ("import_statement", "import_from_statement"):
            continue
        if re.search(rf"\b{re.escape(target_module)}\b", node_text(node)):
            return node.start_point[0] + 1
    return 0
