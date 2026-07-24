"""Go import resolution for the import graph.

A Go package is a directory; an import path resolves (against the go.mod module
prefix) to every non-test .go file in that directory. Stdlib/third-party imports
(outside the module prefix) resolve to nothing. Line attribution is recorded at
resolution time into the returned ImportResult, like the other resolvers.
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING
from enforcer.types import ImportResult, ImportResolver

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder


class GoImportResolver(ImportResolver):
    """Resolves Go imports to the .go files of each imported package.

    What:       given a .go file, returns the non-test .go files its local imports
                resolve to (every such file in each imported package directory)
    Ignores:    stdlib/third-party imports (outside the go.mod module prefix);
                _test.go files as targets; workspaces without a go.mod
    Basis:      AST_GO via FileContextBuilder parse-once cache
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str):
        self.builder = builder
        self.workspace = workspace
        # False = go.mod not yet read; None = no go.mod/module line; str = module path.
        self._module: str | None | bool = False
        self._imports_cache: dict[str, dict[str, int]] = {}

    def resolve(self, path: str) -> ImportResult:
        """Return the .go files a Go file's local imports resolve to, with each edge's line.

        Every resolved target is attributed to the line of the import_spec that produced
        it; all files of one imported package share that package's import line."""
        module = self._module_path()
        if not module:
            return ImportResult()
        targets: set[str] = set()
        lines: dict[str, int] = {}
        for imp, line in self._extract_imports(path).items():
            for target in self._resolve_import(imp, module):
                targets.add(target)
                lines.setdefault(target, line)
        return ImportResult(targets=targets, lines=lines)

    def _extract_imports(self, path: str) -> dict[str, int]:
        """Return {import-path string: 1-based import line} for a Go file. Cached."""
        if path not in self._imports_cache:
            from enforcer.types import Needs
            ctx = self.builder.build(path, force_needs={Needs.AST_GO})
            self._imports_cache[path] = self._import_strings(ctx.ast.root_node) if ctx.ast else {}
        return self._imports_cache[path]

    @staticmethod
    def _import_strings(root) -> dict[str, int]:
        """Collect {quoted path: 1-based line} from every Go import_spec node under root."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        imports: dict[str, int] = {}
        for node in walk_ast(root):
            if node.type != "import_spec":
                continue
            literal = next((c for c in node.children
                            if c.type in ("interpreted_string_literal", "raw_string_literal")), None)
            if literal is not None:
                imports.setdefault(node_text(literal).strip('"`'), node.start_point[0] + 1)
        return imports

    def _resolve_import(self, import_path: str, module: str) -> list[str]:
        """Map a local import path to the non-test .go files in its package directory.

        Only imports under the module prefix are local; stdlib/third-party imports
        resolve to nothing (like unresolvable Python modules).
        """
        rel = self._package_rel(import_path, module)
        if rel is None:
            return []
        pkg_dir = os.path.join(self.workspace, rel) if rel else self.workspace
        if not os.path.isdir(pkg_dir):
            return []
        return self._go_files_in(pkg_dir, rel)

    @staticmethod
    def _package_rel(import_path: str, module: str) -> str | None:
        """Return the package dir relative to workspace for a local import, else None."""
        if import_path == module:
            return ""
        if import_path.startswith(module + "/"):
            return import_path[len(module) + 1:]
        return None

    def _go_files_in(self, pkg_dir: str, rel: str) -> list[str]:
        """Return repo-relative non-test .go files directly in a package directory."""
        files: list[str] = []
        for name in os.listdir(pkg_dir):
            if self._is_go_source(pkg_dir, name):
                files.append(f"{rel}/{name}" if rel else name)
        return files

    @staticmethod
    def _is_go_source(pkg_dir: str, name: str) -> bool:
        """Return True if name is a non-test .go file in pkg_dir."""
        if not name.endswith(".go") or name.endswith("_test.go"):
            return False
        return os.path.isfile(os.path.join(pkg_dir, name))

    def _module_path(self) -> str | None:
        """Return the module path from go.mod at the workspace root, or None. Cached."""
        if self._module is not False:
            return self._module  # type: ignore[return-value]
        self._module = self._parse_go_mod(os.path.join(self.workspace, "go.mod"))
        return self._module

    @staticmethod
    def _parse_go_mod(path: str) -> str | None:
        """Extract the `module <path>` declaration from a go.mod file, or None."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (IOError, OSError, UnicodeDecodeError):
            return None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("module "):
                return stripped[len("module "):].strip()
        return None
