"""DocstringMatcher: flags public functions (not _-prefixed, not __init__) missing docstrings."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import FUNC_NODE_TYPES, find_functions, node_text, declared_name


@dataclass
class DocstringMatcher:
    """Walks AST for function nodes, flags public functions missing docstrings.
    Skips _-prefixed (private, including dunders). Checks if the first statement
    in the function body is an expression_statement containing a string.

    For Go (needs=AST_GO), "public" means exported (upper-case first letter) and a
    docstring means a `//`/`/* */` doc comment on the line directly above the
    declaration (Go's convention), detected as an adjacent preceding comment node.

    For C# (needs=AST_CSHARP), "public" means a `public` access modifier and a
    docstring means a `///` XML doc comment on the line directly above the method.

    What:       flags public functions (Python/TS: name not _-prefixed; Go: exported; C#: public modifier) lacking a docstring/doc comment
    Ignores:    files with no parsed AST; private functions; documented functions
    Basis:      AST_PY (default; AST_GO for Go, AST_CSHARP for C#) — walks file_ctx.ast function nodes
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag public functions missing docstrings in the AST. Returns list of Match."""
        if not file_ctx.ast:
            return []
        is_go = self.needs == Needs.AST_GO
        is_csharp = self.needs == Needs.AST_CSHARP
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in find_functions(root):
            name = declared_name(func_node, csharp=is_csharp)
            if not name or not self._is_public(func_node, name, is_go, is_csharp):
                continue
            documented = self._is_documented(func_node, is_go, is_csharp)
            if not documented:
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=name,
                ))
        return matches

    def _is_public(self, func_node, name: str, is_go: bool, is_csharp: bool) -> bool:
        """Public: C# `public` modifier; Go exported (upper-case first letter); else non _-prefixed."""
        if is_csharp:
            return self._has_public_modifier(func_node)
        if is_go:
            return name[:1].isupper()
        return not name.startswith("_")

    def _is_documented(self, func_node, is_go: bool, is_csharp: bool) -> bool:
        """A function is documented per its language's convention."""
        if is_go:
            return self._has_adjacent_comment(func_node)
        if is_csharp:
            return self._has_adjacent_comment(func_node, prefix="///")
        return self._has_docstring(func_node)

    @staticmethod
    def _has_public_modifier(func_node) -> bool:
        """Return True if a C# declaration carries a `public` access modifier."""
        return any(
            child.type == "modifier" and node_text(child) == "public"
            for child in func_node.children
        )

    @staticmethod
    def _has_adjacent_comment(func_node, prefix: str | None = None) -> bool:
        """A declaration is documented if a comment sits on the line directly above it.

        When `prefix` is given (C# `///`), the comment must start with it to count
        as a doc comment rather than an ordinary line comment.
        """
        prev = func_node.prev_named_sibling
        if prev is None or prev.type != "comment":
            return False
        if func_node.start_point[0] - prev.end_point[0] > 1:
            return False
        if prefix is not None:
            return node_text(prev).lstrip().startswith(prefix)
        return True

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
