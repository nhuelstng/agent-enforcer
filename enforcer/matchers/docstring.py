"""DocstringMatcher: flags public functions (not _-prefixed, not __init__) missing docstrings."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

_FUNC_NODE_TYPES = {
    "function_definition",       # Python def (top-level + class methods)
    "function_declaration",      # TypeScript standalone function + Go top-level func
    "method_definition",         # TypeScript class method
    "method_declaration",        # TypeScript class method (alt grammar) + Go method
}


@dataclass
class DocstringMatcher:
    """Walks AST for function nodes, flags public functions missing docstrings.
    Skips _-prefixed (private, including dunders). Checks if the first statement
    in the function body is an expression_statement containing a string.

    For Go (needs=AST_GO), "public" means exported (upper-case first letter) and a
    docstring means a `//`/`/* */` doc comment on the line directly above the
    declaration (Go's convention), detected as an adjacent preceding comment node.

    What:       flags public functions (Python/TS: name not _-prefixed; Go: exported) lacking a docstring/doc comment
    Ignores:    files with no parsed AST; private (Python/TS _-prefixed, Go unexported) functions; documented functions
    Basis:      AST_PY (default; AST_GO for Go) — walks file_ctx.ast function nodes
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag public functions missing docstrings in the AST. Returns list of Match."""
        if not file_ctx.ast:
            return []
        is_go = self.needs == Needs.AST_GO
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in self._find_functions(root):
            name = self._extract_name(func_node)
            if not name or not self._is_public(name, is_go):
                continue
            documented = self._has_go_doc(func_node) if is_go else self._has_docstring(func_node)
            if not documented:
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=name,
                ))
        return matches

    @staticmethod
    def _is_public(name: str, is_go: bool) -> bool:
        """Public means exported in Go (upper-case first letter), non _-prefixed elsewhere."""
        if is_go:
            return name[:1].isupper()
        return not name.startswith("_")

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
        # ponytail: Go method/function names are field_identifier / identifier direct children
        for child in node.children:
            if child.type in ("identifier", "property_identifier", "field_identifier"):
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    @staticmethod
    def _has_go_doc(func_node) -> bool:
        """A Go declaration is documented if a comment sits on the line directly above it."""
        prev = func_node.prev_named_sibling
        if prev is None or prev.type != "comment":
            return False
        # ponytail: Go doc comments must be adjacent — a blank line breaks the association.
        return func_node.start_point[0] - prev.end_point[0] <= 1

    def _has_docstring(self, func_node) -> bool:
        """Check if function body's first statement is a docstring string."""
        for child in func_node.children:
            if child.type != "block":
                continue
            if not child.children:
                return False
            return self._first_stmt_is_string(child.children[0])
        return False

    @staticmethod
    def _first_stmt_is_string(first_stmt) -> bool:
        """Return True if the expression_statement contains a string node."""
        if first_stmt.type != "expression_statement":
            return False
        return any(gc.type == "string" for gc in first_stmt.children)
