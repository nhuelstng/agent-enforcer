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
        for child in file_ctx.ast.root_node.children:
            m = self._match_for_child(child, file_ctx.path)
            if m is not None:
                matches.append(m)
        return matches

    def _match_for_child(self, child, path: str) -> Match | None:
        """Return a violation Match for a top-level node, or None if it's allowed.

        Comments are ignored; an allowed statement type only offends when it is a
        side-effecting expression (a call); any other top-level type offends outright."""
        if child.type == "comment":
            return None
        line = child.start_point[0] + 1
        if child.type in _ALLOWED_TOP_LEVEL:
            if self._is_side_effect_expression(child):
                return Match(file=path, line=line, matched_value="expression_statement")
            return None
        return Match(file=path, line=line, matched_value=child.type)

    def _is_side_effect_expression(self, node) -> bool:
        if node.type != "expression_statement":
            return False
        return any(c.type == "call" for c in node.children)
