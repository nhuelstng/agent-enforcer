"""AST-aware predicates: HasDecoratorPredicate, NodeNamePredicate."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match

def _get_node_at_line(file_ctx, line: int):
    """Find the declaration AST node starting at the given line (1-indexed)."""
    if not file_ctx or not file_ctx.ast:
        return None
    root = file_ctx.ast.root_node
    # ponytail: walk named children only (skip punctuation tokens), collect candidates at line,
    # prefer declaration node types — function/class/method definitions carry the name identifier
    _DECL = {
        "function_definition", "class_definition", "method_definition",
        "function_declaration", "class_declaration", "method_declaration",
        "variable_declaration",
    }
    candidates = []
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if node.start_point[0] + 1 == line:
            candidates.append((depth, node))
        for child in node.named_children:
            stack.append((child, depth + 1))
    if not candidates:
        return None
    decls = [c for _, c in candidates if c.type in _DECL]
    if decls:
        return decls[0]
    # no declaration — deepest named candidate
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

@dataclass
class HasDecoratorPredicate:
    """Passes if the matched node (or its parent) has a decorator.
    If pattern is set, the decorator text must match it."""
    pattern: str | None = None

    def __post_init__(self):
        if self.pattern:
            self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        ctx = getattr(match, "file_ctx", None) or getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        # ponytail: decorators are siblings BEFORE the decorated node in tree-sitter
        parent = node.parent
        if not parent:
            return False
        idx = parent.children.index(node)
        return self._scan_decorators(parent.children, idx)

    def _scan_decorators(self, siblings: list, idx: int) -> bool:
        """Scan siblings before idx for matching decorators."""
        for i in range(idx - 1, -1, -1):
            sibling = siblings[i]
            if sibling.type == "decorator" and self._matches_decorator(sibling):
                return True
            if sibling.type not in ("decorator", "comment", "newline"):
                break
        return False

    def _matches_decorator(self, sibling) -> bool:
        """Return True if the decorator sibling matches the pattern (or no pattern set)."""
        raw = sibling.text
        text = raw.decode() if hasattr(raw, "decode") else str(raw)
        return not self.pattern or self._compiled.search(text)

@dataclass
class NodeNamePredicate:
    """Passes if the matched node's name matches the regex pattern."""
    pattern: str

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        """Return True if match passes the predicate filter."""
        ctx = getattr(match, "file_ctx", None) or getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        # extract name: first identifier child
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                raw = child.text
                name = raw.decode() if hasattr(raw, "decode") else str(raw)
                return bool(self._compiled.search(name))
        return False
