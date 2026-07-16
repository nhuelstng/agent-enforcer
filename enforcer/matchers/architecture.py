"""ArchitectureMatcher: flags imports crossing forbidden layer or sibling boundaries."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.glob_util import glob_match
from enforcer.parsers.ast_utils import walk_ast, node_text


@dataclass
class ArchitectureMatcher:
    """Flags imports crossing forbidden layer edges or peer-slice boundaries.

    Two independent, composable constraints:

    - **Layer DAG** (`layers` + `allowed_edges`/`forbidden_edges`): flags an
      import when the source file's layer -> target file's layer is not in
      allowed_edges (forbid_implicit=True) or is in forbidden_edges.
    - **Sibling isolation** (`isolate_siblings`): each entry is a parent
      directory whose immediate children are peer "slices" that may not import
      one another. This expresses the vertical-slice invariant ("no cross-slice
      imports") that the layer DAG alone can't — sibling slices matching one
      layer glob collapse to a single layer, so their cross-imports read as
      intra-layer and are skipped. Sibling isolation works with or without any
      declared layer.

    What:       flags import statements whose (source_layer -> target_layer) is
                forbidden, OR that cross a peer-slice boundary under an
                isolate_siblings root
    Ignores:    intra-layer imports; imports between files in the same slice;
                files/targets matching no layer glob and no isolate root;
                unresolvable targets
    Basis:      AST_PY (reads pre-built __import_graph__; line attribution walks AST)
    shared_ctx: reads __import_graph__ (dict[str, set[str]]) built by ImportGraphBuilder
    """
    layers: dict[str, list[str]] = field(default_factory=dict)
    allowed_edges: list[tuple[str, str]] = field(default_factory=list)
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    forbid_implicit: bool = True
    isolate_siblings: list[str] = field(default_factory=list)
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag imports crossing forbidden layer or sibling boundaries. Returns list of Match."""
        shared_ctx = shared_ctx or {}
        graph = shared_ctx.get("__import_graph__", {})
        targets = graph.get(file_ctx.path, set())
        src_layer = self._layer_for_path(file_ctx.path)

        matches: list[Match] = []
        for tgt in targets:
            violation = self._layer_violation(src_layer, tgt) or self._sibling_violation(file_ctx.path, tgt)
            if violation is not None:
                matches.append(Match(
                    file=file_ctx.path,
                    line=self._import_line_for(file_ctx, tgt),
                    matched_value=violation,
                ))
        return matches

    def _layer_violation(self, src_layer: str | None, tgt: str) -> str | None:
        """Return 'src_layer -> tgt_layer' if the edge is forbidden, else None."""
        if src_layer is None:
            return None
        tgt_layer = self._layer_for_path(tgt)
        if tgt_layer is None or tgt_layer == src_layer:
            return None
        edge = (src_layer, tgt_layer)
        return f"{src_layer} -> {tgt_layer}" if self._is_forbidden(edge) else None

    def _sibling_violation(self, src_path: str, tgt_path: str) -> str | None:
        """Return a sibling-boundary message if src and tgt are peer slices, else None."""
        for root in self.isolate_siblings:
            src_slice = self._child_under(src_path, root)
            tgt_slice = self._child_under(tgt_path, root)
            if src_slice and tgt_slice and src_slice != tgt_slice:
                return f"{src_slice} -> {tgt_slice} (sibling slices under {root})"
        return None

    @staticmethod
    def _child_under(path: str, root: str) -> str | None:
        """Return the immediate child segment of `path` under `root`, or None if not under it."""
        prefix = root.rstrip("/") + "/"
        if not path.startswith(prefix):
            return None
        segment = path[len(prefix):].split("/", 1)[0]
        return segment or None

    def _is_forbidden(self, edge: tuple[str, str]) -> bool:
        """Return True if edge is forbidden per allowed/forbidden config."""
        if self.forbid_implicit:
            return edge not in self.allowed_edges
        return edge in self.forbidden_edges

    def _layer_for_path(self, path: str) -> str | None:
        """Return layer name whose globs match path, or None."""
        for layer_name, globs in self.layers.items():
            if any(glob_match(path, g) for g in globs):
                return layer_name
        return None

    def _import_line_for(self, file_ctx: FileContext, target: str) -> int:
        """Walk file_ctx.ast for the import node resolving to target. Returns line or 0."""
        if not file_ctx.ast:
            return 0
        target_module = target.replace("/", ".").removesuffix(".__init__").removesuffix(".py")
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type not in ("import_statement", "import_from_statement"):
                continue
            text = node_text(node)
            # ponytail: word-boundary match on dotted path; avoids mis-attributing enforcer.types inside import enforcer.types_utils
            if re.search(rf"\b{re.escape(target_module)}\b", text):
                return node.start_point[0] + 1
        return 0
