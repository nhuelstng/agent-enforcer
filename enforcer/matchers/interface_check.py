"""InterfaceMatcher: flags classes with >=min_methods public methods that don't inherit a base class."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_FUNC_NODE_TYPES = {
    "function_definition",       # Python def
    "function_declaration",      # TypeScript
    "method_definition",         # TypeScript class method
    "method_declaration",        # TypeScript class method (alt grammar) + C# method
}


@dataclass
class InterfaceMatcher:
    """Walks AST for class nodes, flags classes with >=min_methods public methods and no base class.
    Skips @dataclass-decorated classes — they are config carriers, not behavioral objects.
    Set needs=AST_PY for Python, needs=AST_CSHARP for C#.

    What:       flags non-dataclass classes with >=min_methods public methods and no base type (no inheritance/interface)
    Ignores:    files with no parsed AST; Python dataclasses; C# records (own node type); private/dunder methods and C# non-public methods; classes with <min_methods public methods; classes with a base class or implemented interface
    Basis:      AST_PY (default) / AST_CSHARP — walks class nodes, checks base list + public method count
    shared_ctx: none (defensive default only)
    """
    min_methods: int = 4
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag non-dataclass classes with enough methods but no base class. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        class_type = "class_declaration" if self.needs == Needs.AST_CSHARP else "class_definition"
        for node in walk_ast(root):
            if node.type != class_type:
                continue
            if self._is_dataclass(node):
                continue
            method_count = self._count_methods(node)
            if method_count < self.min_methods:
                continue
            if self._has_base_class(node):
                continue
            name = self._class_name(node)
            matches.append(Match(
                file=file_ctx.path,
                line=node.start_point[0] + 1,
                matched_value=name,
            ))
        return matches

    def _is_dataclass(self, node) -> bool:
        """Check if class has @dataclass decorator (on parent decorated_definition)."""
        parent = node.parent
        if not parent or parent.type != "decorated_definition":
            return False
        return any(
            child.type == "decorator" and "dataclass" in node_text(child)
            for child in parent.children
        )

    def _count_methods(self, node) -> int:
        """Count public methods in the class body (Python: names not starting with '_'; C#: `public` modifier).

        Private helpers and dunders (__init__, _helper) don't count toward the
        interface threshold — a class with a small public API but many private
        helpers doesn't need a base class for substitutability.
        """
        container = "declaration_list" if self.needs == Needs.AST_CSHARP else "block"
        blocks = [c for c in node.children if c.type == container]
        return sum(
            1 for block in blocks for inner in walk_ast(block)
            if inner.type in _FUNC_NODE_TYPES and self._is_public_method(inner)
        )

    def _is_public_method(self, func_node) -> bool:
        """True if the method is public (C#: a `public` modifier; else name not '_'-prefixed)."""
        if self.needs == Needs.AST_CSHARP:
            return any(
                child.type == "modifier" and node_text(child) == "public"
                for child in func_node.children
            )
        name = self._method_name(func_node)
        return bool(name) and not name.startswith("_")

    def _method_name(self, func_node) -> str:
        """Return a function/method node's declared name, or '' if not found."""
        for child in func_node.children:
            if child.type in ("identifier", "property_identifier"):
                return node_text(child)
        return ""

    def _has_base_class(self, node) -> bool:
        """True if the class declares a base type (C#: a base_list; else an argument_list of identifiers)."""
        if self.needs == Needs.AST_CSHARP:
            return any(child.type == "base_list" for child in node.children)
        for child in node.children:
            if child.type == "argument_list":
                return any(c.type == "identifier" for c in child.children)
        return False

    def _class_name(self, node) -> str:
        """Extract class name from the first direct identifier child."""
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return ""
