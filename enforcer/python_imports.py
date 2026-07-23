"""Python import resolution for the import graph.

Resolves `import X.Y` and `from X.Y import Z` to on-disk files relative to the
workspace, honouring source_roots (an import prefix rooted in a subdirectory). A
from-import's final component may be a symbol rather than a submodule; resolution
falls back to the parent package file when the full dotted path has no target.
Relative imports (leading '.') are deferred. Line attribution is recorded at
resolution time into the returned ImportResult.
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING
from enforcer.types import ImportResult, ImportResolver

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder


class PythonImportResolver(ImportResolver):
    """Resolves a Python file's imports to the on-disk modules they name.

    What:       given a .py file, returns the workspace files its imports resolve to
                plus each edge's 1-based import line
    Ignores:    stdlib/third-party modules (no on-disk target); relative imports (deferred)
    Basis:      AST_PY via FileContextBuilder parse-once cache
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str,
                 source_roots: dict[str, str] | None = None):
        self.builder = builder
        self.workspace = workspace
        # ponytail: longest prefix first so 'app.sub' wins over 'app'.
        self.source_roots = dict(
            sorted((source_roots or {}).items(), key=lambda kv: -len(kv[0]))
        )
        self._imports_cache: dict[str, dict[str, int]] = {}

    def resolve(self, path: str) -> ImportResult:
        """Resolve a Python file's imports to target paths, recording import lines."""
        targets: set[str] = set()
        lines: dict[str, int] = {}
        for module, line in self._extract_imports(path).items():
            for target in self._resolve_import(module):
                targets.add(target)
                lines.setdefault(target, line)
        return ImportResult(targets=targets, lines=lines)

    def _extract_imports(self, path: str) -> dict[str, int]:
        """Parse file's imports, return {dotted module-path: 1-based line}. Cached.

        Emits 'X.Y.Z' for 'from X.Y import Z' (Z may be symbol or submodule);
        _resolve_import handles the symbol-vs-submodule distinction by falling
        back to the parent package file when Z is not a submodule on disk.
        """
        if path in self._imports_cache:
            return self._imports_cache[path]
        modules: dict[str, int] = {}
        root = self._root_node(path)
        if root is not None:
            self._collect_modules(root, modules)
        self._imports_cache[path] = modules
        return modules

    def _root_node(self, path: str):
        """Return AST root node for path, or None if unparseable."""
        from enforcer.types import Needs
        ctx = self.builder.build(path, force_needs={Needs.AST_PY})
        if not ctx.ast:
            return None
        return ctx.ast.root_node

    @staticmethod
    def _collect_modules(root, modules: dict[str, int]) -> None:
        """Walk AST, collect {dotted module: 1-based line} (first occurrence wins)."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        for node in walk_ast(root):
            line = node.start_point[0] + 1
            if node.type == "import_statement":
                PythonImportResolver._collect_plain_import(node, node_text, modules, line)
            elif node.type == "import_from_statement":
                PythonImportResolver._collect_from_import(node, node_text, modules, line)

    @staticmethod
    def _dotted_name_text(node, node_text) -> str | None:
        """Return a node's dotted-name text, unwrapping an aliased_import; else None."""
        if node.type == "dotted_name":
            return node_text(node)
        if node.type == "aliased_import":
            sub = next((c for c in node.children if c.type == "dotted_name"), None)
            return node_text(sub) if sub is not None else None
        return None

    @staticmethod
    def _collect_plain_import(node, node_text, modules: dict[str, int], line: int) -> None:
        """Extract modules from 'import X.Y [as z], A.B [as w], ...'.

        One import_statement holds comma-separated modules; each is either a
        bare dotted_name or an aliased_import wrapping a dotted_name.
        """
        for child in node.children:
            name = PythonImportResolver._dotted_name_text(child, node_text)
            if name is not None:
                modules.setdefault(name, line)

    @staticmethod
    def _collect_from_import(node, node_text, modules: dict[str, int], line: int) -> None:
        """Extract modules from 'from X import Y[, Z]'.

        Y/Z may be bare dotted_names or aliased_imports (Y as foo); descend
        into aliased_import children to recover the real imported name.
        """
        children = node.children
        dotted_names = [c for c in children if c.type == "dotted_name"]
        relative = [c for c in children if c.type == "relative_import"]
        if relative or not dotted_names:
            # ponytail: relative import support deferred -- add when repo needs it
            return
        pkg = node_text(dotted_names[0])
        imported = dotted_names[1:] + [c for c in children if c.type == "aliased_import"]
        if not imported:
            modules.setdefault(pkg, line)
            return
        for name_node in imported:
            name = PythonImportResolver._dotted_name_text(name_node, node_text)
            if name is not None:
                modules.setdefault(f"{pkg}.{name}", line)

    def _resolve_import(self, module: str) -> list[str]:
        """Resolve a dotted module string to on-disk paths relative to workspace.

        'pkg.sub' -> ['pkg/sub/__init__.py', 'pkg/sub.py'] (whichever exists).
        For from-imports, the final component may be a symbol (not a submodule);
        fall back to the parent package's file when the full dotted path has no
        on-disk target. Example: 'enforcer.types.Needs' -> 'enforcer/types.py'.
        Relative imports (module starts with '.') deferred.
        """
        if not module or module.startswith("."):
            # ponytail: relative import support deferred -- add when a repo needs it
            return []
        parts = module.split(".")
        disk = self._ondisk_parts(parts)
        candidates: list[str] = [
            os.path.join(*disk, "__init__.py"),
            os.path.join(*disk[:-1], disk[-1] + ".py"),
        ]
        resolved = self._existing(candidates)
        if not resolved and len(parts) >= 2:
            # ponytail: final component is a symbol, not a submodule; fall back to
            # the parent package (its __init__ or .py file).
            parent = self._ondisk_parts(parts[:-1])
            parent_candidates: list[str] = [
                os.path.join(*parent, "__init__.py"),
                os.path.join(*parent[:-1], parent[-1] + ".py"),
            ]
            resolved = self._existing(parent_candidates)
        return resolved

    def _ondisk_parts(self, parts: list[str]) -> list[str]:
        """Map import-path segments to on-disk segments via source_roots.

        The first source root (longest prefix wins) whose dotted key matches the
        leading segments has that prefix replaced by its on-disk directory;
        unmatched imports pass through unchanged. Graph node paths therefore
        stay repo-relative so path globs keep matching.
        """
        for prefix, root_dir in self.source_roots.items():
            pre = prefix.split(".")
            if parts[:len(pre)] == pre:
                return root_dir.strip("/").split("/") + parts[len(pre):]
        return parts

    def _existing(self, candidates: list[str]) -> list[str]:
        """Filter candidate paths to those existing on disk, normalized to /."""
        resolved: list[str] = []
        for cand in candidates:
            full = os.path.join(self.workspace, cand)
            if os.path.isfile(full):
                resolved.append(cand.replace(os.sep, "/"))
        return resolved
