"""Shared AST utilities: iterative walker + node-type constants for Python/TS/Go/C#."""
from __future__ import annotations
import re
from typing import Iterator

FUNC_NODE_TYPES = {
    "function_definition",
    "function_declaration",   # Python? no — TS/JS standalone func + Go top-level func
    "function",               # TS/JS function expression
    "method_definition",
    "method_declaration",     # TS method + Go method (with receiver) + C# method
    "local_function_statement",  # C#: function nested in a method body
}

# ponytail: identifier node types that carry a declaration's name (non-C#).
NAME_IDENTIFIER_TYPES = ("identifier", "type_identifier", "property_identifier", "field_identifier")

# ponytail: declaration node types node_at_line prefers when several nodes start on a line —
# these carry the name identifier a predicate wants. A subset of DECL_NODE_TYPES kept narrow
# on purpose so node_at_line resolves to the outermost named declaration, not any spec/field.
PREFERRED_DECL_TYPES = {
    "function_definition", "class_definition", "method_definition",
    "function_declaration", "class_declaration", "method_declaration",
    "variable_declaration",
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
    "field_declaration",      # Go struct field

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


def declared_name(node, csharp: bool = False) -> str:
    """Return a declaration node's name across languages.

    Python/TS/Go: the first name-bearing identifier child. C#: the identifier
    immediately before the parameter or accessor list (a leading identifier is the
    return/element type); plain C# types (class/interface/struct/enum) fall back to
    the first identifier. Returns "" when no name is found."""
    if csharp:
        return _csharp_declared_name(node)
    for child in node.children:
        if child.type in NAME_IDENTIFIER_TYPES:
            return node_text(child)
    return ""


def _csharp_declared_name(node) -> str:
    """C# name: the identifier before a parameter/accessor list, else the first identifier."""
    member = _csharp_member_name(node)
    if member:
        return member
    for child in node.children:
        if child.type == "identifier":
            return node_text(child)
    return ""


def _csharp_member_name(node) -> str:
    """Return the identifier immediately preceding a parameter_list/accessor_list, or ''."""
    for idx, child in enumerate(node.children):
        if child.type not in ("parameter_list", "accessor_list"):
            continue
        prev = [c for c in node.children[:idx] if c.type == "identifier"]
        if prev:
            return node_text(prev[-1])
    return ""


def node_at_line(root, line: int) -> object | None:
    """Find the declaration AST node starting at the given 1-indexed line, or None.

    Walks named children only (skips punctuation), collects nodes that start on the
    line, and prefers a declaration node type (PREFERRED_DECL_TYPES) — they carry the
    name identifier callers want. Falls back to the deepest named node on the line."""
    if root is None:
        return None
    candidates: list[tuple[int, object]] = []
    stack: list[tuple[int, object]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if node.start_point[0] + 1 == line:
            candidates.append((depth, node))
        for child in node.named_children:
            stack.append((child, depth + 1))
    if not candidates:
        return None
    decls = [c for _, c in candidates if c.type in PREFERRED_DECL_TYPES]
    if decls:
        return decls[0]
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


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
    if target_path.endswith(".cs"):
        # ponytail: C# edges attribute their line via __import_lines__ recorded at
        # resolution (a using->namespace->file mapping isn't recoverable from the
        # target path alone). 0 is the fallback when that record is absent.
        return 0
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
