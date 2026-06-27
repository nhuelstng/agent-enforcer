"""NamingConventionMatcher: walks AST for declarations, checks names against a regex."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs

# ponytail: node types where the name is the first identifier child
_DECL_NODE_TYPES = {
    "function_definition": "function",     # Python def
    "function_declaration": "function",     # TS function
    "method_definition": "method",          # Python/TS method
    "method_declaration": "method",         # TS method declaration
    "class_definition": "class",            # Python class
    "class_declaration": "class",           # TS class
    "variable_declaration": "variable",     # TS const/let/var
}

@dataclass
class NamingConventionMatcher:
    """Walks AST for declaration nodes, flags names that don't match the required pattern.
    declaration_types: which node types to check (e.g. ['function_definition', 'class_definition']).
    pattern: regex the declaration name must match. If it doesn't match, the name is flagged."""
    declaration_types: list[str]
    pattern: str
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk(root):
            if node.type in self.declaration_types and node.type in _DECL_NODE_TYPES:
                name = self._extract_name(node)
                if name and not self._compiled.search(name):
                    matches.append(Match(
                        file=file_ctx.path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1] + 1,
                        matched_value=name,
                    ))
        return matches

    def _extract_name(self, node) -> str:
        # ponytail: name is the first identifier child for most declaration nodes
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    def _walk(self, node):
        # ponytail: iterative DFS — avoids RecursionError on deeply nested AST
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))
