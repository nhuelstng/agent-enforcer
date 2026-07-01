"""NoModuleSideEffectsMatcher: flags module-level statements that cause side effects at import time."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast

_ALLOWED_TOP_LEVEL = {
    "import_statement",
    "import_from_statement",
    "expression_statement",
    "assignment",
    "augmented_assignment",
    "class_definition",
    "function_definition",
    "decorated_definition",
    "comment",
    "if_statement",
    "pass_statement",
    "future_import_statement",
}


@dataclass
class NoModuleSideEffectsMatcher:
    """Walks AST for module-level statements, flags those causing side effects at import time.

    What:       flags module-level statements that aren't imports, assignments, class/function defs, or conditionals
    Ignores:    files with no parsed AST; allowed top-level statement types
    Basis:      AST_PY (walks file_ctx.ast root_node children for disallowed statement types)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag module-level statements causing side effects. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for child in root.children:
            if child.type == "comment":
                continue
            if child.type in _ALLOWED_TOP_LEVEL:
                if self._is_side_effect_expression(child):
                    matches.append(Match(
                        file=file_ctx.path,
                        line=child.start_point[0] + 1,
                        matched_value="expression_statement",
                    ))
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=child.start_point[0] + 1,
                matched_value=child.type,
            ))
        return matches

    def _is_side_effect_expression(self, node) -> bool:
        if node.type != "expression_statement":
            return False
        return any(c.type == "call" for c in node.children)
