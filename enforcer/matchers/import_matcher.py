"""ImportMatcher: walks AST for import statements, matches against forbidden module patterns."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

# ponytail: tree-sitter node types for import statements across languages
_IMPORT_NODE_TYPES = {
    "import_statement",      # Python: import X
    "import_from_statement",  # Python: from X import Y
    "import_declaration",     # TypeScript/JS: import ... from ...
}

@dataclass
class ImportMatcher:
    """Walks the tree-sitter AST for import statements, flags any whose text matches a forbidden regex.
    Set needs=AST_PY for Python files, needs=AST_TS for TypeScript/JS files, needs=AST_GO for Go files.

    What:       flags import statements whose text matches any of `forbidden_patterns`
    Ignores:    files with no parsed AST; non-import nodes; imports that match no forbidden pattern
    Basis:      AST_PY (default; AST_TS when overridden) — walks file_ctx.ast for import_statement/import_from_statement/import_declaration
    shared_ctx: none (defensive default only)
    """
    forbidden_patterns: list[str]
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        # ponytail: pre-compile regexes to avoid recompilation in hot loop
        self._compiled = [re.compile(p) for p in self.forbidden_patterns]

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Walk AST for import statements matching forbidden regex patterns. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk_iterative(root):
            if node.type not in _IMPORT_NODE_TYPES:
                continue
            text = node.text.decode() if isinstance(node.text, bytes) else str(node.text)
            match = self._match_first_pattern(text)
            if match:
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=text.strip(),
                ))
        return matches

    def _match_first_pattern(self, text: str) -> bool:
        """Return True if text matches any compiled forbidden pattern."""
        return any(pattern.search(text) for pattern in self._compiled)

    def _walk_iterative(self, root):
        # ponytail: iterative DFS — avoids RecursionError on deeply nested AST (minified/generated code)
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

