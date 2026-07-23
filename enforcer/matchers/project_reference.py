"""ProjectReferenceMatcher: flags .csproj <ProjectReference> edges crossing forbidden layer boundaries."""
from __future__ import annotations
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.glob_util import glob_match


@dataclass
class ProjectReferenceMatcher:
    """Flags MSBuild ``<ProjectReference>`` edges whose (source layer -> target layer) is forbidden.

    Where ``ArchitectureMatcher`` reasons over the C# *namespace* import graph, this
    matcher reasons over the *project* (assembly) graph declared in ``.csproj``/``.fsproj``
    files. It catches a forbidden reference the moment it is added to a project file —
    before any ``using`` crosses the boundary — which no Roslyn analyzer enforces without
    hand-written architecture tests.

    Each ``<ProjectReference Include="..\\Infra\\Infra.csproj"/>`` resolves to a
    repo-relative target path (relative to the source project's own directory); source and
    target project paths are mapped to layers by glob, and the edge is checked against the
    allowed/forbidden config — the same DAG model ``ArchitectureMatcher`` uses.

    What:       flags a project reference whose (source_layer -> target_layer) is not in
                allowed_edges (forbid_implicit=True) or is in forbidden_edges
    Ignores:    references within one layer; source/target projects matching no layer glob;
                malformed XML; files with no raw text
    Basis:      RAW — parses .csproj/.fsproj XML; resolution is self-contained (no cross-file read)
    shared_ctx: none (defensive default only)
    """
    layers: dict[str, list[str]] = field(default_factory=dict)
    allowed_edges: list[tuple[str, str]] = field(default_factory=list)
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    forbid_implicit: bool = True
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag project references crossing forbidden layer boundaries. Returns list of Match."""
        if not file_ctx.raw:
            return []
        src_layer = self._layer_for_path(file_ctx.path)
        matches: list[Match] = []
        for include in self._project_references(file_ctx.raw):
            target = self._resolve_target(file_ctx.path, include)
            violation = self._layer_violation(src_layer, target)
            if violation is not None:
                matches.append(Match(
                    file=file_ctx.path,
                    line=self._include_line(file_ctx.raw, include),
                    matched_value=violation,
                ))
        return matches

    @staticmethod
    def _project_references(raw: str) -> list[str]:
        """Return the raw Include values of every <ProjectReference> in a project file."""
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        includes: list[str] = []
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "ProjectReference":
                continue
            include = element.get("Include")
            if include:
                includes.append(include)
        return includes

    @staticmethod
    def _resolve_target(source: str, include: str) -> str:
        """Resolve a reference Include (relative, possibly `\\`-separated) to a repo-relative path."""
        rel = include.replace("\\", "/")
        joined = os.path.join(os.path.dirname(source), rel)
        return os.path.normpath(joined).replace(os.sep, "/")

    def _layer_violation(self, src_layer: str | None, target: str) -> str | None:
        """Return 'src_layer -> tgt_layer' if the edge is forbidden, else None."""
        if src_layer is None:
            return None
        tgt_layer = self._layer_for_path(target)
        if tgt_layer is None or tgt_layer == src_layer:
            return None
        edge = (src_layer, tgt_layer)
        return f"{src_layer} -> {tgt_layer}" if self._is_forbidden(edge) else None

    def _is_forbidden(self, edge: tuple[str, str]) -> bool:
        """Return True if edge is forbidden per allowed/forbidden config."""
        if self.forbid_implicit:
            return edge not in self.allowed_edges
        return edge in self.forbidden_edges

    def _layer_for_path(self, path: str) -> str | None:
        """Return the layer name whose globs match path, or None."""
        for layer_name, globs in self.layers.items():
            if any(glob_match(path, g) for g in globs):
                return layer_name
        return None

    @staticmethod
    def _include_line(raw: str, include: str) -> int:
        """Return the 1-based line of the reference declaring `include`, or 0 if not found."""
        pattern = re.compile(r'Include\s*=\s*["\']' + re.escape(include) + r'["\']')
        for idx, line in enumerate(raw.splitlines(), start=1):
            if pattern.search(line):
                return idx
        return 0
