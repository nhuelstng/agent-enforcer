from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommentPerFunctionMatcher:
    max_comments: int
    needs: Needs | None = None

    def find(self, file_ctx: FileContext) -> list[Match]:
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
        for child in node.children:
            if child.type in func_types:
                result.append(child)
            result.extend(self._find_functions(child))
        return result

    def _count_comments(self, func_node) -> int:
        count = 0
        for node in self._walk_all(func_node):
            if "comment" in node.type:
                count += 1
        return count

    def _walk_all(self, node):
        yield node
        for child in node.children:
            yield from self._walk_all(child)
