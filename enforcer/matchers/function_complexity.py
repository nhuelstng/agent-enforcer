"""FunctionComplexityMatcher: walks AST functions, computes lines/params/nesting/cyclomatic complexity."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

# ponytail: tree-sitter node types for functions across languages
_FUNC_NODE_TYPES = {
    "function_definition",       # Python def (top-level + class methods)
    "function_declaration",      # TypeScript standalone function + Go top-level func
    "method_definition",         # TypeScript class method
    "method_declaration",        # TypeScript class method (alt grammar) + Go method (with receiver)
}

_DECISION_NODE_TYPES = {
    "if_statement", "elif_clause", "for_statement", "while_statement",
    "except_clause", "catch_clause", "try_statement",
    "conditional_expression",   # ternary
    "boolean_op",               # Python and/or
    "case_clause",              # match/case
    # Go: each switch/select case is a branch (default excluded, like else/case _)
    "expression_case", "type_case", "communication_case",
}

# ponytail: TS/Go &&/|| are binary_expression nodes — only count when operator is && or ||
_TS_LOGICAL_OPS = {"&&", "||"}

_NESTING_NODE_TYPES = {
    "if_statement", "for_statement", "while_statement",
    "except_clause", "catch_clause", "try_statement",
    "with_statement", "match_statement", "case_clause",
    # Go: switch/select bodies introduce a nesting level
    "expression_switch_statement", "type_switch_statement", "select_statement",
}

# ponytail: param node types across Python + TypeScript
_PARAM_NODE_TYPES = {
    "identifier", "default_parameter", "typed_parameter",
    "typed_default_parameter", "list_splat_pattern", "dictionary_splat_pattern",
    "required_parameter", "optional_parameter", "rest_pattern",
}

# ponytail: Go groups params by type (`a, b int` is one node with two names), so
# count identifiers inside the parameter_list rather than the declaration nodes.
_GO_PARAM_DECL_TYPES = {"parameter_declaration", "variadic_parameter_declaration"}

@dataclass
class FunctionComplexityMatcher:
    """Walks the AST for function/method nodes, computes a complexity metric, emits if over threshold.
    Set needs=AST_PY for Python, needs=AST_TS for TypeScript, needs=AST_GO for Go.

    What:       flags functions whose `metric` (lines/params/nesting/cyclomatic) exceeds `max_value`
    Ignores:    files with no parsed AST; __init__ methods (params metric only); nested functions (analyzed independently); functions at or below threshold
    Basis:      AST_PY (default; AST_TS when overridden) — walks file_ctx.ast function nodes
    shared_ctx: none (defensive default only)
    """
    metric: str  # "lines", "params", "nesting", "cyclomatic"
    max_value: int
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag functions whose complexity metric exceeds the configured maximum. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for func_node in self._find_functions(root):
            if self.metric == "params" and self._is_init(func_node):
                continue
            value = self._compute(func_node)
            if value > self.max_value:
                matches.append(Match(
                    file=file_ctx.path,
                    line=func_node.start_point[0] + 1,
                    matched_value=str(value),
                ))
        return matches

    def _is_init(self, func_node) -> bool:
        """Check if function node is __init__ (constructors exempt from param count)."""
        for child in func_node.children:
            if child.type == "identifier":
                raw = child.text
                name = raw.decode() if hasattr(raw, "decode") else str(raw)
                return name == "__init__"
        return False

    def _find_functions(self, root) -> list:
        # ponytail: iterative DFS — avoids RecursionError on deep ASTs
        result = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in _FUNC_NODE_TYPES:
                result.append(node)
            stack.extend(reversed(node.children))
        return result

    def _compute(self, func_node) -> int:
        if self.metric == "lines":
            return func_node.end_point[0] - func_node.start_point[0] + 1
        if self.metric == "params":
            return self._count_params(func_node)
        if self.metric == "nesting":
            return self._max_depth(func_node, 1)
        if self.metric == "cyclomatic":
            return self._cyclomatic(func_node)
        return 0

    def _count_params(self, func_node) -> int:
        params = self._params_node(func_node)
        if params is None:
            return 0
        if any(c.type in _GO_PARAM_DECL_TYPES for c in params.children):
            return self._count_go_params(params)
        return sum(1 for c in params.children if c.type in _PARAM_NODE_TYPES)

    @staticmethod
    def _params_node(func_node):
        """Return the parameter container node, or None.

        For Go the params list is the first `parameter_list` *after* the function
        name — a leading `parameter_list` is the method receiver and a trailing one
        is the (parenthesised) results. Python/TS expose a single named container.
        """
        seen_name = False
        for child in func_node.children:
            if child.type in ("identifier", "field_identifier"):
                seen_name = True
            elif child.type == "parameter_list" and seen_name:
                return child
            elif child.type in ("parameters", "formal_parameters"):
                return child
        return None

    @staticmethod
    def _count_go_params(params) -> int:
        """Count Go parameters: each declaration groups one or more identifiers by type."""
        total = 0
        for decl in params.children:
            if decl.type not in _GO_PARAM_DECL_TYPES:
                continue
            names = sum(1 for c in decl.children if c.type == "identifier")
            total += names or 1  # an unnamed result/param declaration still counts as one
        return total

    def _max_depth(self, root, start: int) -> int:
        # ponytail: iterative DFS — avoids RecursionError, skips nested functions
        max_d = start
        stack = [(root, start)]
        while stack:
            node, depth = stack.pop()
            if depth > max_d:
                max_d = depth
            stack.extend(
                (child, depth + 1 if child.type in _NESTING_NODE_TYPES else depth)
                for child in reversed(node.children)
                if child.type not in _FUNC_NODE_TYPES
            )
        return max_d

    def _cyclomatic(self, func_node) -> int:
        # ponytail: cyclomatic = 1 + decision points. Skip nested functions — they get their own analysis.
        count = 1
        for node in self._walk_iterative(func_node):
            if node.type in _DECISION_NODE_TYPES:
                count += 1
            elif node.type == "binary_expression" and self._has_ts_logical_op(node):
                count += 1
        return count

    @staticmethod
    def _has_ts_logical_op(node) -> bool:
        """Return True if a binary_expression node contains a TS && or || operator."""
        return any(child.type in _TS_LOGICAL_OPS for child in node.children)

    def _walk_iterative(self, root):
        # ponytail: iterative DFS — avoids RecursionError, skips nested functions (they get their own analysis)
        stack = list(reversed(root.children))
        while stack:
            node = stack.pop()
            if node.type in _FUNC_NODE_TYPES:
                continue  # skip nested functions
            yield node
            stack.extend(reversed(node.children))
