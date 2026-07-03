"""FacadeExposesInterfaceMatcher: flags facade files with no Protocol/ABC interface declaration."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text


@dataclass
class FacadeExposesInterfaceMatcher:
    """Flags facade files that don't expose a public interface (Protocol/ABC in Python).

    What:       flags files with no class(Protocol) or class(ABC) declaration,
                and no non-empty __all__ re-export
    Ignores:    files with no parsed AST; files with a Protocol/ABC class; files with __all__
    Basis:      AST_PY (walks file_ctx.ast for class_definition with Protocol/ABC bases)
    shared_ctx: none
    """
    interface_bases: tuple[str, ...] = ("Protocol", "ABC")
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag if no interface declaration found. Returns list of Match."""
        if not file_ctx.ast:
            return []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if self._is_interface_decl(node):
                return []
            if self._is_reexport_all(node):
                return []
        return [Match(
            file=file_ctx.path,
            line=1,
            matched_value="no interface exposed",
        )]

    def _is_interface_decl(self, node) -> bool:
        """Return True if node is a class_definition with an interface base (Protocol/ABC)."""
        if node.type != "class_definition":
            return False
        arg_list = next((c for c in node.children if c.type == "argument_list"), None)
        if arg_list is None:
            return False
        return any(
            arg.type == "identifier" and node_text(arg) in self.interface_bases
            for arg in arg_list.children
        )

    def _is_reexport_all(self, node) -> bool:
        """Return True if node is a non-empty __all__ assignment (heuristic re-export)."""
        # ponytail: heuristic — __all__ = [...] presence means "this is a facade with public API"
        if node.type != "assignment":
            return False
        left = node.child_by_field_name("left")
        if not left or node_text(left) != "__all__":
            return False
        right = node.child_by_field_name("right")
        if not right:
            return False
        # non-empty list/tuple
        text = node_text(right)
        return bool(text.strip("[]() \n\t"))
