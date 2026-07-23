"""EndpointAuthMatcher: flags ASP.NET minimal-API endpoints registered without an inline auth guard."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_DEFAULT_ENDPOINT_METHODS = (
    "MapGet", "MapPost", "MapPut", "MapDelete", "MapPatch", "MapMethods",
)
_DEFAULT_GUARD_METHODS = ("RequireAuthorization", "AllowAnonymous")
# ponytail: node types that make up a fluent call chain; climbing stops outside them.
_CHAIN_TYPES = {"member_access_expression", "invocation_expression"}


@dataclass
class EndpointAuthMatcher:
    """Flags minimal-API endpoint registrations (`app.MapGet(...)`) with no inline auth guard.

    An endpoint is *guarded* when its registration call is chained into a
    `.RequireAuthorization()` or `.AllowAnonymous()` in the same fluent expression —
    ``app.MapGet("/x", H).RequireAuthorization()``. A bare ``app.MapGet("/x", H)`` ships
    unauthenticated, which the compiler and stock analyzers never flag. This is the
    minimal-API counterpart to the ``[Authorize]``-on-controllers rule.

    What:       flags a Map{Get,Post,...} endpoint call whose fluent chain contains no
                RequireAuthorization/AllowAnonymous call
    Ignores:    files with no parsed AST; non-endpoint calls; endpoints guarded inline;
                guards applied out-of-band (a stored endpoint or a MapGroup guard) — a
                documented false-positive boundary, tune via guard_methods/endpoint_methods
    Basis:      AST_CSHARP — walks invocation_expression nodes, climbs the fluent chain
    shared_ctx: none (defensive default only)
    """
    endpoint_methods: tuple[str, ...] = _DEFAULT_ENDPOINT_METHODS
    guard_methods: tuple[str, ...] = _DEFAULT_GUARD_METHODS
    needs: Needs = Needs.AST_CSHARP

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag endpoint registrations lacking an inline auth guard. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type != "invocation_expression":
                continue
            name = self._invoked_name(node)
            if name in self.endpoint_methods and not self._is_guarded(node):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    matched_value=name,
                ))
        return matches

    def _is_guarded(self, node) -> bool:
        """True if an ancestor invocation in the same fluent chain calls a guard method."""
        current = node.parent
        while current is not None and current.type in _CHAIN_TYPES:
            if current.type == "invocation_expression" and \
                    self._invoked_name(current) in self.guard_methods:
                return True
            current = current.parent
        return False

    @staticmethod
    def _invoked_name(node) -> str:
        """Return the method name an invocation_expression calls (last name after the dot)."""
        func = next((c for c in node.named_children), None)
        if func is None:
            return ""
        if func.type == "member_access_expression":
            names = [c for c in func.children if c.type in ("identifier", "generic_name")]
            return node_text(names[-1]) if names else ""
        if func.type in ("identifier", "generic_name"):
            return node_text(func)
        return ""
