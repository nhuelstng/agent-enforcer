"""InvocationMatcher: flags method/function calls whose callee text matches a pattern."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

# ponytail: the call-expression node type per language grammar
_CALL_NODE_TYPES = {
    Needs.AST_CSHARP: "invocation_expression",
    Needs.AST_PY: "call",
    Needs.AST_TS: "call_expression",
    Needs.AST_GO: "call_expression",
}

_ARG_NODE_TYPES = ("argument_list", "arguments")


@dataclass
class InvocationMatcher:
    """Walks the AST for call expressions, flags those whose callee text matches `pattern`.
    Set needs=AST_CSHARP for C#, AST_PY/AST_TS/AST_GO for other languages.

    The callee is the call's function expression — the member-access chain or
    identifier before the argument list (e.g. ``db.Users.ToList`` for
    ``db.Users.ToList()``). Match against it to ban specific calls: sync-over-async
    (``\\.Wait$``, ``\\.GetResult$``), synchronous EF Core (``\\.ToList$``), or a
    service locator (``GetService``).

    What:       flags call expressions whose callee text matches `pattern`
    Ignores:    files with no parsed AST; property access without a call (e.g. `.Result`); calls whose callee does not match
    Basis:      AST_CSHARP (default) / AST_PY / AST_TS / AST_GO — walks call nodes
    shared_ctx: none (defensive default only)
    """
    pattern: str
    needs: Needs = Needs.AST_CSHARP

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag call expressions whose callee text matches the pattern. Returns list of Match."""
        if not file_ctx.ast:
            return []
        call_type = _CALL_NODE_TYPES.get(self.needs)
        if call_type is None:
            return []
        matches: list[Match] = []
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type != call_type:
                continue
            callee = self._callee_text(node)
            if callee and self._compiled.search(callee):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=callee,
                ))
        return matches

    @staticmethod
    def _callee_text(node) -> str:
        """Return the text of the call's function expression (the child before the args)."""
        for child in node.children:
            if child.type in _ARG_NODE_TYPES:
                break
            return node_text(child)
        return ""
