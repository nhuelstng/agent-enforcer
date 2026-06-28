"""DocstringMatcher: flags public functions (not _-prefixed, not __init__) missing docstrings."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

_FUNC_NODE_TYPES = {
    "function_definition",       # Python def (top-level + class methods)
    "function_declaration",      # TypeScript standalone function
    "method_definition",         # TypeScript class method
    "method_declaration",        # TypeScript class method (alt grammar)
}


@dataclass
class DocstringMatcher:
    """Walks AST for function nodes, flags public functions missing docstrings.
    Skips _-prefixed (private, including dunders). Checks if the first statement
    in the function body is an expression_statement containing a string."""
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag public functions missing docstrings in the AST. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in self._find_functions(root):
            name = self._extract_name(func_node)
            if not name or name.startswith("_"):
                continue
            if not self._has_docstring(func_node):
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=name,
                ))
        return matches

    def _find_functions(self, root) -> list:
        result: list = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in _FUNC_NODE_TYPES:
                result.append(node)
            stack.extend(reversed(node.children))
        return result

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type in ("identifier", "property_identifier"):
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    def _has_docstring(self, func_node) -> bool:
        for child in func_node.children:
            if child.type == "block":
                if not child.children:
                    return False
                first = child.children[0]
                if first.type == "expression_statement":
                    for gc in first.children:
                        if gc.type == "string":
                            return True
                return False
        return False
