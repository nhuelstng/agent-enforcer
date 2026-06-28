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
    Set needs=AST_PY for Python files, needs=AST_TS for TypeScript/JS files."""
    forbidden_patterns: list[str]
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        # ponytail: pre-compile regexes to avoid recompilation in hot loop
        self._compiled = [re.compile(p) for p in self.forbidden_patterns]

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk_iterative(root):
            if node.type in _IMPORT_NODE_TYPES:
                text = node.text.decode() if isinstance(node.text, bytes) else str(node.text)
                for pattern in self._compiled:
                    if pattern.search(text):
                        matches.append(Match(
                            file=file_ctx.path,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1] + 1,
                            matched_value=text.strip(),
                        ))
                        break
        return matches

    def _walk_iterative(self, root):
        # ponytail: iterative DFS — avoids RecursionError on deeply nested AST (minified/generated code)
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

