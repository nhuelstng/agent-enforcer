"""TypeHintMatcher: flags public functions missing return type annotations."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_FUNC_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
}


@dataclass
class TypeHintMatcher:
    """Walks AST for function nodes, flags public functions missing return type annotations.

    What:       flags public functions (not _-prefixed) whose definition lacks a -> return type annotation
    Ignores:    files with no parsed AST; private/dunder functions; functions with return type annotations
    Basis:      AST_PY (walks file_ctx.ast for function_definition nodes and checks for type sub-node)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag public functions missing return type annotations. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type not in _FUNC_NODE_TYPES:
                continue
            name = self._extract_name(node)
            if not name or name.startswith("_"):
                continue
            if self._has_return_type(node):
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=node.start_point[0] + 1,
                matched_value=name,
            ))
        return matches

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type in ("identifier", "property_identifier"):
                return node_text(child)
        return ""

    def _has_return_type(self, node) -> bool:
        for child in node.children:
            if child.type in ("type", "return_type", "type_annotation"):
                return True
        return False
