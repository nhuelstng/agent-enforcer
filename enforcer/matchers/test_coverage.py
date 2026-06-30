"""TestCoverageMatcher: AST-inspects test files for positive+negative parameterized coverage."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

# ponytail: tree-sitter list element node types for counting parametrize cases
_LIST_ELEM_TYPES = {"string", "identifier", "integer", "true", "false", "none"}

# ponytail: method-name keywords signaling test intent when assert text is ambiguous
_POSITIVE_NAME_KEYWORDS = ("fail", "flag", "violation")
_NEGATIVE_NAME_KEYWORDS = ("success", "clean", "valid", "passes")


@dataclass
class TestCoverageMatcher:
    """Inspects a test file's AST for positive + negative test coverage, each parameterized >=3.

    What:       flags test files missing positive (assert) or negative (assert not) cases, or with <3 parametrize cases
    Ignores:    non-test files; test classes with both sides parameterized >=3
    Basis:      AST_PY (tree-sitter AST, iterative DFS for class/method/parametrize detection)
    shared_ctx: none (stateless, reads file_ctx.ast)
    """
    min_parametrize_cases: int = 3
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag test files missing positive or negative parameterized coverage. Returns list of Match."""
        if not file_ctx.ast:
            return []
        from enforcer.parsers.ast_utils import walk_ast

        root = file_ctx.ast.root_node
        has_positive = False
        has_negative = False
        positive_param_count = 0
        negative_param_count = 0

        for node in walk_ast(root):
            if node.type != "function_definition":
                continue
            method_name = self._extract_name(node)
            if not method_name or not method_name.startswith("test_"):
                continue
            is_positive, is_negative, param_count = self._classify_method(node)
            if is_positive:
                has_positive = True
                positive_param_count = max(positive_param_count, param_count)
            if is_negative:
                has_negative = True
                negative_param_count = max(negative_param_count, param_count)

        matches: list[Match] = []
        matches.extend(self._side_matches(file_ctx, has_positive, positive_param_count, "positive"))
        matches.extend(self._side_matches(file_ctx, has_negative, negative_param_count, "negative"))
        return matches

    def _side_matches(self, file_ctx, has_side, param_count, side_name) -> list[Match]:
        """Emit match for a missing or under-parameterized test side (positive/negative)."""
        if has_side and param_count >= self.min_parametrize_cases:
            return []
        if not has_side:
            return [Match(
                file=file_ctx.path, line=0,
                matched_value=f"missing {side_name} test (assert on match list, parametrized >=3)",
                message=f"No {side_name} test case found.",
            )]
        return [Match(
            file=file_ctx.path, line=0,
            matched_value=f"{side_name} test parametrized with {param_count} cases (min {self.min_parametrize_cases})",
            message=f"{side_name.capitalize()} case under-parameterized.",
        )]

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                from enforcer.parsers.ast_utils import node_text
                return node_text(child)
        return ""

    def _classify_method(self, method_node) -> tuple[bool, bool, int]:
        """Return (is_positive, is_negative, parametrize_case_count) for a method node."""
        is_positive, is_negative = self._detect_assert_type(method_node)
        param_count = self._detect_parametrize_count(method_node)
        name = self._extract_name(method_node)
        if not is_positive and any(kw in name for kw in _POSITIVE_NAME_KEYWORDS):
            is_positive = True
        if not is_negative and any(kw in name for kw in _NEGATIVE_NAME_KEYWORDS):
            is_negative = True
        return is_positive, is_negative, param_count

    def _detect_parametrize_count(self, method_node) -> int:
        """Count top-level list elements in @pytest.mark.parametrize decorator.

        Decorators live on the parent `decorated_definition` node, not the function itself.
        """
        from enforcer.parsers.ast_utils import walk_ast, node_text
        search_root = method_node.parent or method_node
        for inner in walk_ast(search_root):
            if inner.type != "decorator":
                continue
            dec_text = node_text(inner)
            if "parametrize" not in dec_text:
                continue
            for sub in walk_ast(inner):
                if sub.type != "list":
                    continue
                return sum(1 for c in sub.children if c.type in _LIST_ELEM_TYPES)
        return 0

    def _detect_assert_type(self, method_node) -> tuple[bool, bool]:
        """Return (is_positive, is_negative) by scanning assert statements in the method."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        is_positive = False
        is_negative = False
        for inner in walk_ast(method_node):
            if inner.type != "assert_statement":
                continue
            assert_text = node_text(inner)
            if "assert not " in assert_text or ("assert len(" in assert_text and "== 0" in assert_text):
                is_negative = True
            elif "assert " in assert_text:
                is_positive = True
        return is_positive, is_negative
