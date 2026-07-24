"""ConstantNamingMatcher: flags module-level constants not named UPPER_CASE."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import node_text


@dataclass
class ConstantNamingMatcher:
    """Walks AST for module-level assignments, flags non-private constants not in UPPER_CASE.

    What:       flags module-level variables (not _-prefixed) that are not UPPER_CASE
    Ignores:    files with no parsed AST; private variables (_-prefixed); already UPPER_CASE names
    Basis:      AST_PY (walks file_ctx.ast root_node children for assignment nodes)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag module-level constants not in UPPER_CASE. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for child in root.children:
            assign = self._unwrap_assignment(child)
            if assign is None:
                continue
            name = self._extract_target_name(assign)
            if not name or name.startswith("_"):
                continue
            if re.match(r'^[A-Z][A-Z0-9_]*$', name):
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=child.start_point[0] + 1,
                matched_value=name,
            ))
        return matches

    def _unwrap_assignment(self, node):
        if node.type == "assignment":
            return node
        if node.type != "expression_statement":
            return None
        return next((c for c in node.children if c.type == "assignment"), None)

    def _extract_target_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return ""
