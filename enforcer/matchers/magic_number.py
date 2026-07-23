"""MagicNumberMatcher: flags magic numeric literals (integers outside -5..5) outside constant assignments."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_ALLOWED_INTS = frozenset(range(-5, 6))

_INT_NODE_TYPES = ("integer", "integer_literal")
_LITERAL_NODE_TYPES = ("integer", "float", "integer_literal", "real_literal")

# ponytail: C# member bodies where a magic literal is worth flagging. Class-field
# initializers, enum members and attribute arguments live outside these and are
# treated like Python's module level — skipped.
_CSHARP_BODY_TYPES = {
    "method_declaration", "constructor_declaration", "destructor_declaration",
    "local_function_statement", "operator_declaration",
    "conversion_operator_declaration", "accessor_declaration",
}
_CSHARP_CONST_MODIFIERS = {"const", "readonly"}


@dataclass
class MagicNumberMatcher:
    """Walks AST for numeric literals, flags magic numbers outside constant assignments.
    Set needs=AST_PY for Python, needs=AST_CSHARP for C#.

    What:       flags numeric literals (integers outside -5..5, all floats) in function/method bodies, not in constants or parameter defaults
    Ignores:    files with no parsed AST; integers in -5..5; Python: UPPER_CASE constant assignments, keyword arguments, module-level assignments; C#: const/readonly declarations, parameter defaults, attribute arguments, enum members, class-field initializers
    Basis:      AST_PY (default) / AST_CSHARP — walks file_ctx.ast for numeric literal nodes
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag magic numbers outside constant assignments. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type not in _LITERAL_NODE_TYPES:
                continue
            if not self._is_magic(node):
                continue
            if node.type in _INT_NODE_TYPES and self._is_allowed_int(node):
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=node.start_point[0] + 1,
                matched_value=node_text(node),
            ))
        return matches

    def _is_magic(self, node) -> bool:
        """True if the literal is in a flaggable position for the target language."""
        if self.needs == Needs.AST_CSHARP:
            return self._is_csharp_magic(node)
        return not (
            self._is_in_constant_assignment(node)
            or self._is_in_parameter_default(node)
            or self._is_in_keyword_argument(node)
            or self._is_module_level(node)
        )

    def _is_csharp_magic(self, node) -> bool:
        """True if a C# literal sits inside a member body and is not a named constant.

        A magic literal counts only inside method/constructor/accessor bodies —
        parameter defaults, attribute arguments, enum members and class-field
        initializers are excluded, as are const/readonly declarations.
        """
        in_body = False
        parent = node.parent
        while parent:
            if parent.type in ("parameter", "attribute", "enum_member_declaration"):
                return False
            if parent.type in ("local_declaration_statement", "field_declaration") \
                    and self._has_const_modifier(parent):
                return False
            if parent.type in _CSHARP_BODY_TYPES:
                in_body = True
            parent = parent.parent
        return in_body

    @staticmethod
    def _has_const_modifier(node) -> bool:
        """True if a declaration node carries a const/readonly modifier child."""
        return any(
            child.type == "modifier" and node_text(child) in _CSHARP_CONST_MODIFIERS
            for child in node.children
        )

    def _is_in_constant_assignment(self, node) -> bool:
        parent = node.parent
        while parent:
            if self._is_constant_assignment(parent):
                return True
            parent = parent.parent
        return False

    @staticmethod
    def _is_constant_assignment(parent) -> bool:
        """True if `parent` is an assignment to an ALL_CAPS constant name."""
        if parent.type != "assignment":
            return False
        target = parent.children[0] if parent.children else None
        if not target or target.type != "identifier":
            return False
        return bool(re.match(r'^[A-Z][A-Z0-9_]*$', node_text(target)))

    def _is_in_parameter_default(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("parameters", "default_parameter", "typed_parameter"):
                return True
            parent = parent.parent
        return False

    def _is_in_keyword_argument(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type == "keyword_argument":
                return True
            parent = parent.parent
        return False

    def _is_module_level(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("function_definition", "function_declaration", "method_definition", "method_declaration"):
                return False
            if parent.parent is None:
                return True
            parent = parent.parent
        return False

    def _is_allowed_int(self, node) -> bool:
        try:
            val = int(node_text(node))
            return val in _ALLOWED_INTS
        except ValueError:
            return False
