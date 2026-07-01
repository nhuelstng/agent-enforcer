"""ArchitectureMatcher: flags imports crossing forbidden layer boundaries."""
from __future__ import annotations
import fnmatch
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs


def _glob_match(path: str, pattern: str) -> bool:
    # ponytail: local copy of enforcer.rule._glob_match — avoids cross-module private import
    candidates = {pattern}
    candidates.add(re.sub(r"/\*\*", "", pattern))
    candidates.add(re.sub(r"\*\*/", "", pattern))
    candidates.add(pattern.replace("**", "*"))
    return any(fnmatch.fnmatch(path, c) for c in candidates)


@dataclass
class ArchitectureMatcher:
    """Flags imports where (source_layer, target_layer) crosses forbidden boundaries.

    What:       flags import statements where source file's layer -> target file's layer
                is not in allowed_edges (forbid_implicit=True) or is in forbidden_edges
    Ignores:    intra-layer imports; files not matching any layer glob; unresolvable targets
    Basis:      AST_PY (reads pre-built __import_graph__; line attribution walks AST)
    shared_ctx: reads __import_graph__ (dict[str, set[str]]) built by ImportGraphBuilder
    """
    layers: dict[str, list[str]] = field(default_factory=dict)
    allowed_edges: list[tuple[str, str]] = field(default_factory=list)
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    forbid_implicit: bool = True
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        # ponytail: precompute layer glob list for ordered lookup; first match wins
        self._layer_globs: list[tuple[str, list[str]]] = list(self.layers.items())

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag imports crossing forbidden layer boundaries. Returns list of Match."""
        shared_ctx = shared_ctx or {}
        graph = shared_ctx.get("__import_graph__", {})
        targets = graph.get(file_ctx.path, set())
        src_layer = self._layer_for_path(file_ctx.path)
        if src_layer is None:
            return []

        matches: list[Match] = []
        for tgt in targets:
            tgt_layer = self._layer_for_path(tgt)
            if tgt_layer is None:
                continue
            if tgt_layer == src_layer:
                continue
            edge = (src_layer, tgt_layer)
            if self._is_forbidden(edge):
                matches.append(Match(
                    file=file_ctx.path,
                    line=self._import_line_for(file_ctx, tgt),
                    matched_value=f"{src_layer} -> {tgt_layer}",
                ))
        return matches

    def _is_forbidden(self, edge: tuple[str, str]) -> bool:
        """Return True if edge is forbidden per allowed/forbidden config."""
        if self.forbid_implicit:
            return edge not in self.allowed_edges
        return edge in self.forbidden_edges

    def _layer_for_path(self, path: str) -> str | None:
        """Return layer name whose globs match path, or None."""
        for layer_name, globs in self._layer_globs:
            if any(_glob_match(path, g) for g in globs):
                return layer_name
        return None

    def _import_line_for(self, file_ctx: FileContext, target: str) -> int:
        """Walk file_ctx.ast for the import node resolving to target. Returns line or 0."""
        if not file_ctx.ast:
            return 0
        from enforcer.parsers.ast_utils import walk_ast, node_text
        target_module = target.replace("/", ".").removesuffix(".__init__").removesuffix(".py")
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type not in ("import_statement", "import_from_statement"):
                continue
            text = node_text(node)
            # ponytail: substring match on the dotted path; precise resolution lives in ImportGraphBuilder
            if target_module in text or target.replace("/__init__.py", "").replace("/", ".") in text:
                return node.start_point[0] + 1
        return 0
