"""C# namespace resolution for the import graph.

C# `using X.Y;` references a namespace, not a file path, so resolution needs a
workspace-wide {namespace: [declaring files]} index rather than the path-based
lookups Python/TS/Go use. The index is built once (lazily) by scanning every
.cs file under the workspace; a using then resolves to each file declaring that
exact namespace (C# `using Foo` imports Foo, not its sub-namespaces).
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING
from enforcer.types import ImportResult, ImportResolver

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder

# Directories skipped when indexing C# namespaces (build output, deps, VCS).
_SKIP_DIRS = {"bin", "obj", ".git", "node_modules", "packages", ".vs"}
_NS_TYPES = ("namespace_declaration", "file_scoped_namespace_declaration")


class CSharpNamespaceResolver(ImportResolver):
    """Resolves C# `using` directives to the workspace files declaring each namespace.

    What:       given a .cs file, returns the files its usings resolve to (files
                declaring the used namespaces) plus each resolved edge's using line
    Ignores:    usings of namespaces declared nowhere in the workspace (external
                assemblies); self-edges; build/dependency directories
    Basis:      AST_CSHARP via FileContextBuilder parse-once cache
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str):
        self.builder = builder
        self.workspace = workspace
        self._index: dict[str, list[str]] | None = None
        self._usings_cache: dict[str, dict[str, int]] = {}

    def resolve(self, path: str) -> ImportResult:
        """Return the files a C# file's usings resolve to, with each using's line."""
        index = self._namespace_index()
        resolved: set[str] = set()
        lines: dict[str, int] = {}
        for namespace, line in self._extract_usings(path).items():
            self._add_targets(index.get(namespace, ()), path, line, resolved, lines)
        return ImportResult(targets=resolved, lines=lines)

    @staticmethod
    def _add_targets(targets, source: str, line: int,
                     resolved: set[str], lines: dict[str, int]) -> None:
        """Add each declaring file (except the source itself) as a resolved edge."""
        for target in targets:
            if target == source:
                continue
            resolved.add(target)
            lines.setdefault(target, line)

    def _extract_usings(self, path: str) -> dict[str, int]:
        """Return {imported namespace: 1-based using line} for a C# file. Cached."""
        if path not in self._usings_cache:
            from enforcer.types import Needs
            ctx = self.builder.build(path, force_needs={Needs.AST_CSHARP})
            root = ctx.ast.root_node if ctx.ast else None
            self._usings_cache[path] = self._using_names(root) if root else {}
        return self._usings_cache[path]

    @staticmethod
    def _using_names(root) -> dict[str, int]:
        """Collect {namespace: line} from every using_directive under root.

        The imported namespace is the directive's last name node, so `using X.Y;`,
        `using static X.Y;`, `global using X.Y;`, and `alias = X.Y` all yield X.Y.
        """
        from enforcer.parsers.ast_utils import walk_ast, node_text
        names: dict[str, int] = {}
        for node in walk_ast(root):
            if node.type != "using_directive":
                continue
            name_nodes = [c for c in node.children if c.type in ("identifier", "qualified_name")]
            if name_nodes:
                names.setdefault(node_text(name_nodes[-1]).strip(), node.start_point[0] + 1)
        return names

    def _namespace_index(self) -> dict[str, list[str]]:
        """Return the workspace {namespace: [declaring files]} index. Built once."""
        if self._index is None:
            self._index = self._scan_namespaces()
        return self._index

    def _scan_namespaces(self) -> dict[str, list[str]]:
        """Walk the workspace's .cs files, mapping each declared namespace to its files."""
        from enforcer.types import Needs
        index: dict[str, list[str]] = {}
        for rel in self._iter_cs_files():
            ctx = self.builder.build(rel, force_needs={Needs.AST_CSHARP})
            root = ctx.ast.root_node if ctx.ast else None
            for namespace in (self._namespaces_in(root) if root else ()):
                index.setdefault(namespace, []).append(rel)
        return index

    def _iter_cs_files(self):
        """Yield repo-relative .cs paths under the workspace, skipping build/dep dirs."""
        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for rel in self._cs_paths_in(root, files):
                yield rel

    def _cs_paths_in(self, root: str, files: list[str]):
        """Yield repo-relative paths of the .cs files in one directory."""
        for name in files:
            if name.endswith(".cs"):
                rel = os.path.relpath(os.path.join(root, name), self.workspace)
                yield rel.replace(os.sep, "/")

    @staticmethod
    def _namespaces_in(root) -> set[str]:
        """Return the set of fully-qualified namespace names declared under root."""
        from enforcer.parsers.ast_utils import walk_ast
        names: set[str] = set()
        for node in walk_ast(root):
            full = CSharpNamespaceResolver._full_name(node) if node.type in _NS_TYPES else ""
            if full:
                names.add(full)
        return names

    @staticmethod
    def _full_name(node) -> str:
        """Return a namespace node's ancestor-qualified name (nested `Outer.Inner`)."""
        parts: list[str] = []
        current = node
        while current is not None:
            if current.type in _NS_TYPES:
                parts.append(CSharpNamespaceResolver._own_name(current))
            current = current.parent
        return ".".join(p for p in reversed(parts) if p)

    @staticmethod
    def _own_name(node) -> str:
        """Return a namespace node's own dotted name (excluding ancestor namespaces)."""
        from enforcer.parsers.ast_utils import node_text
        for child in node.children:
            if child.type in ("identifier", "qualified_name"):
                return node_text(child).strip()
        return ""
