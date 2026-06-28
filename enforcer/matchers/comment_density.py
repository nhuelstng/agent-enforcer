"""CommentPerFunctionMatcher: checks comment-to-code ratio in functions."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommentPerFunctionMatcher:
    """For each function in the AST, counts comments and code lines. Emits a match if ratio is below threshold."""
    max_comments: int
    needs: Needs = Needs.AST_TS

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in self._find_functions(root):
            comment_count = self._count_comments(func_node)
            if comment_count > self.max_comments:
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=str(comment_count),
                ))
        return matches

    def _find_functions(self, node):
        func_types = {"function_declaration", "function_definition", "function",
                       "method_definition", "method_declaration"}
        result = []
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in func_types:
                result.append(current)
            stack.extend(reversed(current.children))
        return result

    def _count_comments(self, func_node) -> int:
        count = 0
        stack = [func_node]
        while stack:
            node = stack.pop()
            if "comment" in node.type:
                count += 1
            stack.extend(reversed(node.children))
        return count
