"""ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from __future__ import annotations
import os
import sys
from abc import ABC
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder


class ImportGraphBuilder(ABC):
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
        queue: deque[str] = deque(staged_files)
        seen: set[str] = set()
        queued: set[str] = set(staged_files)

        self._process_queue(queue, seen, queued, graph)
        self._warn_if_capped(seen)
        return graph

    def _process_queue(self, queue: deque[str], seen: set[str],
                       queued: set[str], graph: dict[str, set[str]]) -> None:
        """Drain queue, populating graph. Stops at max_files cap."""
        while queue and len(seen) < self.max_files:
            path = queue.popleft()
            queued.discard(path)
            if path in seen or not path.endswith(".py"):
                continue
            if not os.path.isfile(os.path.join(self.workspace, path)):
                continue
            seen.add(path)
            resolved = self._resolve_for_path(path)
            self._enqueue_new(resolved, seen, queued, queue)
            graph[path] = resolved

    @staticmethod
    def _enqueue_new(resolved: set[str], seen: set[str],
                     queued: set[str], queue: deque[str]) -> None:
        """Queue resolved targets not already seen or queued."""
        for r in resolved:
            if r not in seen and r not in queued:
                queue.append(r)
                queued.add(r)

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
            resolved.update(self._resolve_import(tgt))
        return resolved

    def _extract_imports(self, path: str) -> set[str]:
        """Parse file's imports, return set of dotted module-path strings. Cached.

        Emits 'X.Y.Z' for 'from X.Y import Z' (Z may be symbol or submodule).
        _resolve_import handles the symbol-vs-submodule distinction by falling
        back to the parent package file when Z is not a submodule on disk.
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
        """Extract modules from 'import X.Y [as z], A.B [as w], ...'.

        One import_statement holds comma-separated modules; each is either a
        bare dotted_name or an aliased_import wrapping a dotted_name.
        """
        for child in node.children:
            if child.type == "dotted_name":
                modules.add(node_text(child))
            elif child.type == "aliased_import":
                sub = next((cc for cc in child.children if cc.type == "dotted_name"), None)
                if sub is not None:
                    modules.add(node_text(sub))

    @staticmethod
    def _collect_from_import(node, node_text, modules: set[str]) -> None:
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
            modules.add(pkg)
            return
        for name_node in imported:
            if name_node.type == "aliased_import":
                sub = next((cc for cc in name_node.children if cc.type == "dotted_name"), None)
                if sub is None:
                    continue
                name_node = sub
            modules.add(f"{pkg}.{node_text(name_node)}")

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
        candidates: list[str] = [
            os.path.join(*parts, "__init__.py"),
            os.path.join(*parts[:-1], parts[-1] + ".py"),
        ]
        resolved = self._existing(candidates)
        if not resolved and len(parts) >= 2:
            # ponytail: final component is a symbol, not a submodule; fall back to
            # the parent package (its __init__ or .py file).
            parent = parts[:-1]
            parent_candidates: list[str] = [
                os.path.join(*parent, "__init__.py"),
                os.path.join(*parent[:-1], parent[-1] + ".py"),
            ]
            resolved = self._existing(parent_candidates)
        return resolved

    def _existing(self, candidates: list[str]) -> list[str]:
        """Filter candidate paths to those existing on disk, normalized to /."""
        resolved: list[str] = []
        for cand in candidates:
            full = os.path.join(self.workspace, cand)
            if os.path.isfile(full):
                resolved.append(cand.replace(os.sep, "/"))
        return resolved
