"""AstNodeMatcher: finds AST nodes matching a type and optional scope."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AstNodeMatcher:
    """Walks the tree-sitter AST, finds nodes of a given type within an optional scope (e.g., function, class)."""
    node_type: str
    scope: str | None = None
    needs: Needs = Needs.AST_TS

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk(root, scope=self.scope):
            if node.type == self.node_type:
                raw = node.text
                text = raw.decode() if isinstance(raw, bytes) else str(raw)
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=text,
                ))
        return matches

    def _walk(self, node, scope=None):
        result = []
        if scope:
            for child in node.children:
                if self._is_scope_node(child, scope):
                    result.extend(self._walk_all(child))
                else:
                    result.extend(self._walk(child, scope=scope))
        else:
            result.extend(self._walk_all(node))
        return result

    def _is_scope_node(self, node, scope: str) -> bool:
        type_map = {
            "class": {"class_declaration", "class_definition", "class"},
            "function": {"function_declaration", "function_definition",
                          "method_definition"},
            "module": {"program"},
        }
        return node.type in type_map.get(scope, set())

    def _walk_all(self, node):
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))
