"""Shared AST utilities: iterative walker + node-type constants for Python/TS/Go/C#."""
from __future__ import annotations
import re
from typing import Iterator

FUNC_NODE_TYPES = {
    "function_definition",
    "function_declaration",   # Python? no — TS/JS standalone func + Go top-level func
    "method_definition",
    "method_declaration",     # TS method + Go method (with receiver) + C# method
    "local_function_statement",  # C#: function nested in a method body
}

DECL_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "class_definition",
    "class_declaration",
    "variable_declaration",
    # Go: declarations wrap named specs; both the wrapper and the spec are listed
    # so callers can target whichever granularity they need.
    "type_declaration",
    "type_spec",
    "const_declaration",
    "const_spec",
    "var_declaration",
    "var_spec",
    "short_var_declaration",
    # C#: type and member declarations
    "interface_declaration",
    "struct_declaration",
    "enum_declaration",
    "record_declaration",
    "property_declaration",
    "local_function_statement",
    "namespace_declaration",
}

IMPORT_NODE_TYPES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",     # TS/JS import + Go import block
    "import_spec",            # Go: a single import within the block
    "using_directive",        # C#: using X.Y;
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
    to 'import pkg.billing'. Go targets ('.go' files) are matched by package
    directory against the import spec's path string.
    """
    if root is None:
        return 0
    if target_path.endswith(".go"):
        return _go_import_line(root, target_path)
    target_module = target_path.replace("/", ".").removesuffix(".__init__").removesuffix(".py")
    for node in walk_ast(root):
        if node.type not in ("import_statement", "import_from_statement"):
            continue
        if re.search(rf"\b{re.escape(target_module)}\b", node_text(node)):
            return node.start_point[0] + 1
    return 0


def _go_import_line(root, target_path: str) -> int:
    """Return the line of the Go import_spec whose path resolves to target_path's package dir."""
    target_dir = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
    for node in walk_ast(root):
        if node.type != "import_spec":
            continue
        literal = next((c for c in node.children
                        if c.type in ("interpreted_string_literal", "raw_string_literal")), None)
        if literal is None:
            continue
        import_path = node_text(literal).strip('"`')
        # ponytail: the import path is <module>/<target_dir>; match on the dir suffix.
        if target_dir and (import_path == target_dir or import_path.endswith("/" + target_dir)):
            return node.start_point[0] + 1
    return 0
