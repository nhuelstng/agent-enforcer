"""TypeScript/JS import resolution for the import graph.

Only relative specifiers ('./', '../') are local; bare ('rxjs') and aliased
('@angular/core', tsconfig paths) specifiers resolve to nothing, like an
unresolvable Python module. A specifier resolves to the first on-disk file among
<base><ext> then <base>/index<ext> (TS module-resolution order). Line attribution
is recorded at resolution time into the returned ImportResult.
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING
from enforcer.types import ImportResult, ImportResolver

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder

# TS/JS files the graph traverses, and the order relative specifiers resolve
# against (a bare 'foo' import tries foo.ts, then foo.tsx, ...).
TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_TS_RESOLVE_EXTS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mts", ".cts")


class TsImportResolver(ImportResolver):
    """Resolves a TS/JS file's relative imports to on-disk files.

    What:       given a TS/JS file, returns the files its relative imports resolve to
                plus each edge's 1-based import line
    Ignores:    bare and aliased specifiers (unresolvable); dynamic import() (deferred)
    Basis:      AST_TS via FileContextBuilder parse-once cache
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str):
        self.builder = builder
        self.workspace = workspace
        self._imports_cache: dict[str, dict[str, int]] = {}

    def resolve(self, path: str) -> ImportResult:
        """Resolve a TS/JS file's relative imports, recording each import's line."""
        targets: set[str] = set()
        lines: dict[str, int] = {}
        for spec, line in self._extract_ts_imports(path).items():
            target = self._resolve_ts_import(spec, path)
            if target is not None:
                targets.add(target)
                lines.setdefault(target, line)
        return ImportResult(targets=targets, lines=lines)

    def _extract_ts_imports(self, path: str) -> dict[str, int]:
        """Return {module specifier: 1-based line} for a TS/JS file. Cached."""
        if path in self._imports_cache:
            return self._imports_cache[path]
        from enforcer.types import Needs
        ctx = self.builder.build(path, force_needs={Needs.AST_TS})
        specs = self._ts_import_specs(ctx.ast.root_node) if ctx.ast else {}
        self._imports_cache[path] = specs
        return specs

    @staticmethod
    def _ts_import_specs(root) -> dict[str, int]:
        """Collect {specifier: line} from every import/export statement's source string.

        The module source is the direct `string` child of an import_statement or a
        re-exporting export_statement (`export ... from '...'`); an `export const x
        = "s"` nests its string deeper, so direct children only avoids false hits.
        """
        from enforcer.parsers.ast_utils import walk_ast, node_text
        specs: dict[str, int] = {}
        for node in walk_ast(root):
            if node.type not in ("import_statement", "export_statement"):
                continue
            src = next((c for c in node.children if c.type == "string"), None)
            if src is not None:
                specs.setdefault(node_text(src).strip("'\"`"), node.start_point[0] + 1)
        return specs

    def _resolve_ts_import(self, spec: str, src_path: str) -> str | None:
        """Resolve a relative TS specifier to an on-disk file, or None if unresolvable."""
        if not (spec.startswith("./") or spec.startswith("../")):
            return None
        src_dir = os.path.dirname(src_path)
        base = os.path.normpath(os.path.join(src_dir, spec)).replace(os.sep, "/")
        for cand in self._ts_candidates(base):
            if os.path.isfile(os.path.join(self.workspace, cand)):
                return cand
        return None

    @staticmethod
    def _ts_candidates(base: str) -> list[str]:
        """Ordered on-disk candidates for a TS import base path (file, then dir index)."""
        cands: list[str] = []
        if base.endswith(_TS_RESOLVE_EXTS):
            cands.append(base)
        cands.extend(base + ext for ext in _TS_RESOLVE_EXTS)
        cands.extend(f"{base}/index{ext}" for ext in _TS_RESOLVE_EXTS)
        return cands
