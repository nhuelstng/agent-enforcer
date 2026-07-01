"""MagicNumberMatcher: flags magic numeric literals (integers outside -5..5) outside constant assignments."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_ALLOWED_INTS = frozenset(range(-5, 6))


@dataclass
class MagicNumberMatcher:
    """Walks AST for numeric literals, flags magic numbers outside constant assignments.

    What:       flags numeric literals (integers outside -5..5, all floats) in function bodies, not in assignments or parameter defaults
    Ignores:    files with no parsed AST; integers in -5..5; numbers in UPPER_CASE constant assignments; parameter defaults; keyword arguments; module-level assignments
    Basis:      AST_PY (walks file_ctx.ast for integer/float literal nodes)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag magic numbers outside constant assignments. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type not in ("integer", "float"):
                continue
            if self._is_in_constant_assignment(node):
                continue
            if self._is_in_parameter_default(node):
                continue
            if self._is_in_keyword_argument(node):
                continue
            if self._is_module_level(node):
                continue
            if node.type == "integer" and self._is_allowed_int(node):
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=node.start_point[0] + 1,
                matched_value=node_text(node),
            ))
        return matches

    def _is_in_constant_assignment(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type == "assignment":
                target = parent.children[0] if parent.children else None
                if target and target.type == "identifier":
                    name = node_text(target)
                    if re.match(r'^[A-Z][A-Z0-9_]*$', name):
                        return True
            parent = parent.parent
        return False

    def _is_in_parameter_default(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("parameters", "default_parameter", "typed_parameter"):
                return True
            parent = parent.parent
        return False

    def _is_in_keyword_argument(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type == "keyword_argument":
                return True
            parent = parent.parent
        return False

    def _is_module_level(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("function_definition", "function_declaration", "method_definition", "method_declaration"):
                return False
            if parent.parent is None:
                return True
            parent = parent.parent
        return False

    def _is_allowed_int(self, node) -> bool:
        try:
            val = int(node_text(node))
            return val in _ALLOWED_INTS
        except ValueError:
            return False
