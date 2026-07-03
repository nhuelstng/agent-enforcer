"""InterfaceMatcher: flags classes with >=min_methods methods that don't inherit a base class."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_FUNC_NODE_TYPES = {
    "function_definition",       # Python def
    "function_declaration",      # TypeScript
    "method_definition",         # TypeScript class method
    "method_declaration",        # TypeScript class method (alt grammar)
}


@dataclass
class InterfaceMatcher:
    """Walks AST for class nodes, flags classes with >=min_methods that have no base class.
    Skips @dataclass-decorated classes — they are config carriers, not behavioral objects.

    What:       flags non-dataclass classes with >=min_methods methods and no base class (no inheritance)
    Ignores:    files with no parsed AST; dataclass-decorated classes; classes with <min_methods; classes with base classes
    Basis:      AST_PY (walks file_ctx.ast for class_definition nodes, checks decorators + argument_list + method count)
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
        for node in walk_ast(root):
            if node.type != "class_definition":
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
        """Count function_definition nodes directly in the class block."""
        blocks = [c for c in node.children if c.type == "block"]
        return sum(
            1 for block in blocks for inner in walk_ast(block)
            if inner.type in _FUNC_NODE_TYPES
        )

    def _has_base_class(self, node) -> bool:
        """Check if class has base classes (argument_list with identifiers)."""
        for child in node.children:
            if child.type == "argument_list":
                return any(c.type == "identifier" for c in child.children)
        return False

    def _class_name(self, node) -> str:
        """Extract class name from identifier child."""
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return ""
