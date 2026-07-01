"""ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from __future__ import annotations
import os
import sys
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder


@runtime_checkable
class ImportGraphBuilderProtocol(Protocol):
    """Public contract for import-graph builders: build graph, resolve modules."""

    def build(self, staged_files: list[str]) -> dict[str, set[str]]:
        """Return import graph for staged files plus transitive closure."""
        ...


class ImportGraphBuilder(ImportGraphBuilderProtocol):
    """Builds {source_path: set[target_path]} from staged files + transitive closure.

    What:       resolves Python imports (import X.Y, from X.Y import Z) to on-disk paths.
    Ignores:    stdlib/third-party (unresolvable -> not in graph). relative imports (deferred).
    Basis:      AST_PY via FileContextBuilder parse-once cache.
    shared_ctx: none (standalone builder; consumers may stash result under __import_graph__).
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str = ".",
                 max_files: int = 500):
        self.builder = builder
        self.workspace = workspace
        self.max_files = max_files
        # ponytail: parse-once cache keyed by path; reuses builder but also
        # holds imports extracted per file to avoid re-walking AST
        self._imports_cache: dict[str, set[str]] = {}

    def build(self, staged_files: list[str]) -> dict[str, set[str]]:
        """Build import graph from staged files + transitive closure. Returns graph dict."""
        graph: dict[str, set[str]] = {}
        queue: list[str] = list(staged_files)
        seen: set[str] = set()

        self._process_queue(queue, seen, graph)
        self._warn_if_capped(seen)
        return graph

    def _process_queue(self, queue: list[str], seen: set[str],
                       graph: dict[str, set[str]]) -> None:
        """Drain queue, populating graph. Stops at max_files cap."""
        while queue and len(seen) < self.max_files:
            path = queue.pop(0)
            if path in seen or not path.endswith(".py"):
                continue
            seen.add(path)
            resolved = self._resolve_for_path(path)
            self._enqueue_new(resolved, seen, queue)
            graph[path] = resolved

    @staticmethod
    def _enqueue_new(resolved: set[str], seen: set[str], queue: list[str]) -> None:
        """Queue resolved targets not already seen or queued."""
        for r in resolved:
            if r not in seen and r not in queue:
                queue.append(r)

    def _warn_if_capped(self, seen: set[str]) -> None:
        """Emit stderr warning when max_files cap was reached."""
        if len(seen) >= self.max_files:
            sys.stderr.write(
                f"[enforcer] import graph cap ({self.max_files}) reached; "
                f"closure truncated. Staged files still fully checked.\n"
            )

    def _resolve_for_path(self, path: str) -> set[str]:
        """Extract imports for path and resolve each to on-disk target paths."""
        resolved: set[str] = set()
        targets = self._extract_imports(path)
        for tgt in targets:
            resolved.update(self._resolve_import(path, tgt))
        return resolved

    def _extract_imports(self, path: str) -> set[str]:
        """Parse file's imports, return set of module-path strings. Cached.

        For 'from X import Y' where Y resolves as submodule X.Y, emits 'X.Y'.
        Falls back to package 'X' when X.Y has no on-disk target.
        """
        if path in self._imports_cache:
            return self._imports_cache[path]
        modules: set[str] = set()
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
    def _collect_modules(root, modules: set[str]) -> None:
        """Walk AST, collect dotted module strings into modules set."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        for node in walk_ast(root):
            if node.type == "import_statement":
                ImportGraphBuilder._collect_plain_import(node, node_text, modules)
            elif node.type == "import_from_statement":
                ImportGraphBuilder._collect_from_import(node, node_text, modules)

    @staticmethod
    def _collect_plain_import(node, node_text, modules: set[str]) -> None:
        """Extract module from 'import X.Y [as z]'."""
        dotted = [c for c in node.children if c.type == "dotted_name"]
        if dotted:
            modules.add(node_text(dotted[0]))
            return
        aliased = next((c for c in node.children if c.type == "aliased_import"), None)
        if aliased is None:
            return
        sub = [cc for cc in aliased.children if cc.type == "dotted_name"]
        if sub:
            modules.add(node_text(sub[0]))

    @staticmethod
    def _collect_from_import(node, node_text, modules: set[str]) -> None:
        """Extract modules from 'from X import Y[, Z]'."""
        children = node.children
        dotted_names = [c for c in children if c.type == "dotted_name"]
        relative = [c for c in children if c.type == "relative_import"]
        if relative or not dotted_names:
            # ponytail: relative import support deferred -- add when repo needs it
            return
        pkg = node_text(dotted_names[0])
        imported_names = dotted_names[1:]
        if not imported_names:
            modules.add(pkg)
            return
        for name_node in imported_names:
            modules.add(f"{pkg}.{node_text(name_node)}")
        modules.add(pkg)

    def _resolve_import(self, source_path: str, module: str) -> list[str]:
        """Resolve a dotted module string to on-disk paths relative to workspace.

        'pkg.sub' -> ['pkg/sub/__init__.py', 'pkg/sub.py'] (whichever exists).
        Relative imports (module starts with '.') resolved against source package.
        """
        if not module or module.startswith("."):
            # ponytail: relative import support deferred -- add when a repo needs it
            return []
        parts = module.split(".")
        candidates: list[str] = []
        candidates.append(os.path.join(*parts, "__init__.py"))
        py_path = os.path.join(*parts[:-1], parts[-1] + ".py") if parts else ""
        if py_path:
            candidates.append(py_path)
        if len(parts) == 1:
            candidates.append(parts[0] + ".py")
        return self._existing(candidates)

    def _existing(self, candidates: list[str]) -> list[str]:
        """Filter candidate paths to those existing on disk, normalized to /."""
        resolved: list[str] = []
        for cand in candidates:
            full = os.path.join(self.workspace, cand)
            if os.path.isfile(full):
                resolved.append(cand.replace(os.sep, "/"))
        return resolved
