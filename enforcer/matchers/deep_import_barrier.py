"""DeepImportBarrierMatcher: flags cross-module imports that bypass a module's facade."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.check_context import CheckContext
from enforcer.glob_util import glob_match


@dataclass
class DeepImportBarrierMatcher:
    """Flags imports that cross into a module but land below its declared entry points.

    Symbol-agnostic, path-shaped encapsulation: `module_glob` names the directory
    level that delimits an encapsulated module (each match is one module), and
    `entry_points` are the only paths *within* a module a foreign file may import.
    An import crossing from one module into another must resolve to one of the
    target module's entry points; anything deeper is a facade-bypassing deep import.

    Composes with ArchitectureMatcher — that governs *which* module boundaries may
    be crossed; this governs *where* a permitted crossing may land.

    What:       flags cross-module edges whose target is not one of the target
                module's entry points (e.g. pkg/b/internal.py when only
                pkg/b/__init__.py is exported)
    Ignores:    intra-module imports; edges whose target is in no governed module;
                edges that land on an entry point; unresolvable targets
    Basis:      AST_PY/AST_TS/AST_GO/AST_CSHARP (reads pre-built __import_graph__; line via __import_lines__)
    shared_ctx: reads __import_graph__ (dict[str, set[str]]) and __import_lines__, built by ImportGraphBuilder
    """
    module_glob: str = ""
    entry_points: list[str] = field(default_factory=lambda: ["__init__.py"])
    needs: Needs = Needs.AST_PY
    reads_import_graph = True  # marker: check_runner builds __import_graph__ when present

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag cross-module imports that bypass the target module's facade. Returns list of Match."""
        ctx = CheckContext.of(shared_ctx)
        graph = ctx.import_graph
        import_lines = ctx.import_lines.get(file_ctx.path, {})
        src_module = self._module_of(file_ctx.path)

        matches: list[Match] = []
        for tgt in graph.get(file_ctx.path, set()):
            tgt_module = self._module_of(tgt)
            if tgt_module is None or tgt_module == src_module:
                continue
            if self._is_entry_point(tgt, tgt_module):
                continue
            matches.append(Match(
                file=file_ctx.path,
                line=import_lines.get(tgt, 0),
                matched_value=f"{tgt} (deep import into {tgt_module}; import its entry point)",
            ))
        return matches

    def _module_of(self, path: str) -> str | None:
        """Return the module-root directory `path` lives under, or None.

        The module root is the path prefix up to and including the first
        wildcard segment of `module_glob` (e.g. 'pkg/*' -> 'pkg/<child>'). A file
        must live strictly inside that directory to belong to the module.
        """
        glob_segs = self.module_glob.split("/")
        star_idx = next((i for i, s in enumerate(glob_segs) if "*" in s or "?" in s), None)
        if star_idx is None:
            return None
        path_segs = path.split("/")
        if len(path_segs) <= star_idx + 1:
            return None
        for i in range(star_idx + 1):
            if not fnmatch.fnmatch(path_segs[i], glob_segs[i]):
                return None
        return "/".join(path_segs[:star_idx + 1])

    def _is_entry_point(self, target: str, module_root: str) -> bool:
        """Return True if target is one of module_root's declared entry points."""
        prefix = module_root.rstrip("/") + "/"
        return any(glob_match(target, prefix + ep) for ep in self.entry_points)
