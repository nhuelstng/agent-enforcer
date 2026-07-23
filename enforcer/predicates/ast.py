"""AST-aware predicates: HasDecoratorPredicate, HasAttributePredicate, HasBaseTypePredicate, AttributeArgumentPredicate, NodeNamePredicate."""
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
class HasAttributePredicate:
    """Passes if the matched C# declaration carries an attribute (e.g. [ApiController]).
    If pattern is set, the attribute text must match it.

    The C# analogue of HasDecoratorPredicate. A C# `attribute_list` node is a
    child of the declaration it annotates (unlike a Python decorator, which is a
    preceding sibling), so this scans the matched node's own children, then its
    parent's, to cover a match that lands on an inner identifier. It never climbs
    past the parent, so an attribute on an enclosing type is not mis-attributed to
    an undecorated member inside it."""
    pattern: str | None = None

    def __post_init__(self):
        if self.pattern:
            self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        """Return True if the match's declaration (or its parent) has a matching attribute."""
        ctx = getattr(match, "file_ctx", None) or getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        return self._scan(node) or (node.parent is not None and self._scan(node.parent))

    def _scan(self, node) -> bool:
        """True if any direct `attribute_list` child of node matches the pattern."""
        return any(
            child.type == "attribute_list" and self._matches(child)
            for child in node.children
        )

    def _matches(self, attr_list) -> bool:
        """Return True if the attribute_list text matches the pattern (or no pattern set)."""
        raw = attr_list.text
        text = raw.decode() if hasattr(raw, "decode") else str(raw)
        return not self.pattern or self._compiled.search(text)

_BASE_CONTAINER_TYPES = ("base_list", "class_heritage", "argument_list")

@dataclass
class HasBaseTypePredicate:
    """Passes if the matched class declares a base type (base class or interface)
    whose text matches the pattern. With no pattern, passes when any base is present.

    Language-agnostic: reads a C# `base_list`, a TypeScript `class_heritage`, or a
    Python class `argument_list`. Unlike HasAttributePredicate it never inspects the
    parent, so a match must land on the class declaration itself. Enables rules like
    'controllers must derive ControllerBase' or 'handlers must implement IRequestHandler'."""
    pattern: str | None = None

    def __post_init__(self):
        if self.pattern:
            self._compiled = re.compile(self.pattern)

    def test(self, match: Match) -> bool:
        """Return True if the matched class has a base type matching the pattern."""
        ctx = getattr(match, "file_ctx", None) or getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        for child in node.children:
            if child.type not in _BASE_CONTAINER_TYPES:
                continue
            raw = child.text
            text = raw.decode() if hasattr(raw, "decode") else str(raw)
            if not self.pattern or self._compiled.search(text):
                return True
        return False

@dataclass
class AttributeArgumentPredicate:
    """Passes if the C# attribute named `attribute` on the matched declaration carries
    at least one argument. If arg_pattern is set, the argument list text must also match it.

    Structural — reads the `attribute_argument_list` rather than the raw attribute text,
    so nested calls and quoted strings don't confuse it. Enables rules like '[Route] must
    specify a template' or '[ProducesResponseType] must declare a status code'."""
    attribute: str
    arg_pattern: str | None = None

    def __post_init__(self):
        self._attr = re.compile(self.attribute)
        self._arg = re.compile(self.arg_pattern) if self.arg_pattern else None

    def test(self, match: Match) -> bool:
        """Return True if the named attribute is present with matching argument(s)."""
        ctx = getattr(match, "file_ctx", None) or getattr(match, "_file_ctx", None)
        node = _get_node_at_line(ctx, match.line) if ctx else None
        if not node:
            return False
        return any(
            self._attribute_has_args(attr)
            for attr_list in node.children if attr_list.type == "attribute_list"
            for attr in attr_list.children if attr.type == "attribute"
        )

    def _attribute_has_args(self, attr) -> bool:
        """True if this attribute matches `attribute` and has a matching argument list."""
        if not self._attr.search(self._attribute_name(attr)):
            return False
        arg_list = next((c for c in attr.children if c.type == "attribute_argument_list"), None)
        if arg_list is None or not any(c.type == "attribute_argument" for c in arg_list.children):
            return False
        raw = arg_list.text
        text = raw.decode() if hasattr(raw, "decode") else str(raw)
        return self._arg is None or bool(self._arg.search(text))

    @staticmethod
    def _attribute_name(attr) -> str:
        """Return the attribute's name (identifier or qualified_name child)."""
        for child in attr.children:
            if child.type in ("identifier", "qualified_name"):
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

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
