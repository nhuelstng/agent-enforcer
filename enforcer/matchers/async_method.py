"""AsyncMethodMatcher: flags C# async-convention violations (async void, Task methods not named *Async)."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_TASK_RETURN_PREFIXES = ("Task", "ValueTask")


@dataclass
class AsyncMethodMatcher:
    """Walks the C# AST for method declarations, flags async-convention violations.

    Two checks (select via `check`):

    - ``no_async_void``: an ``async`` method returning ``void``. Such methods can't
      be awaited and swallow exceptions; only event handlers should use them.
    - ``task_suffix``: a method returning ``Task``/``Task<T>``/``ValueTask`` whose
      name does not end in ``Async`` (the .NET TAP naming convention).

    What:       flags async void methods, or Task-returning methods not named *Async
    Ignores:    files with no parsed AST; constructors/accessors (no return type); non-matching methods; the other check's concern
    Basis:      AST_CSHARP — walks method_declaration nodes
    shared_ctx: none (defensive default only)
    """
    check: str  # "no_async_void" | "task_suffix"
    needs: Needs = Needs.AST_CSHARP

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag async-convention violations per the configured check. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type != "method_declaration":
                continue
            name, return_type = self._name_and_return(node)
            if self._violates(node, name, return_type):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    matched_value=name or "<method>",
                ))
        return matches

    def _violates(self, node, name: str, return_type: str) -> bool:
        """Return True if the method violates the configured check."""
        if self.check == "no_async_void":
            return self._is_async(node) and return_type == "void"
        if self.check == "task_suffix":
            return self._returns_task(return_type) and not name.endswith("Async")
        return False

    @staticmethod
    def _is_async(node) -> bool:
        """True if the method carries an `async` modifier."""
        return any(
            child.type == "modifier" and node_text(child) == "async"
            for child in node.children
        )

    @staticmethod
    def _returns_task(return_type: str) -> bool:
        """True if the return type is Task / Task<T> / ValueTask / ValueTask<T>."""
        return return_type.startswith(_TASK_RETURN_PREFIXES)

    @staticmethod
    def _name_and_return(node) -> tuple[str, str]:
        """Return (method name, return-type text). Name is the identifier before the
        parameter/type-parameter list; the return type is the child just before it."""
        boundary = None
        for idx, child in enumerate(node.children):
            if child.type in ("parameter_list", "type_parameter_list"):
                boundary = idx
                break
        if boundary is None:
            return "", ""
        name_idx = next((i for i in range(boundary - 1, -1, -1)
                         if node.children[i].type == "identifier"), None)
        if name_idx is None:
            return "", ""
        name = node_text(node.children[name_idx])
        return_type = node_text(node.children[name_idx - 1]) if name_idx > 0 else ""
        return name, return_type
