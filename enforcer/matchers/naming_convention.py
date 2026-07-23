"""NamingConventionMatcher: walks AST for declarations, checks names against a regex."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import DECL_NODE_TYPES, walk_ast, declared_name

@dataclass
class NamingConventionMatcher:
    """Walks AST for declaration nodes, flags names that don't match the required pattern.
    declaration_types: which node types to check (e.g. ['function_definition', 'class_definition']).
    pattern: regex the declaration name must match. If it doesn't match, the name is flagged.

    What:       flags declaration names (functions/classes/variables per declaration_types) that don't match `pattern`
    Ignores:    files with no parsed AST; declaration node types not in declaration_types; nodes with no extractable identifier; names that match
    Basis:      AST_PY (default; AST_TS when overridden) — walks file_ctx.ast for declaration nodes
    shared_ctx: none (defensive default only)
    """
    declaration_types: list[str]
    pattern: str
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag declaration names that don't match the required regex pattern. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type not in self.declaration_types or node.type not in DECL_NODE_TYPES:
                continue
            name = declared_name(node, csharp=self.needs == Needs.AST_CSHARP)
            if name and not self._compiled.search(name):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=name,
                ))
        return matches
