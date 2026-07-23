"""ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from __future__ import annotations
import os
import sys
from collections import deque
from typing import TYPE_CHECKING
from enforcer.types import ImportResolver
from enforcer.ts_imports import TS_EXTS as _TS_EXTS

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder

# C# source files the graph traverses. C# usings reference namespaces (not file
# paths); enforcer.csharp_imports resolves them via a workspace namespace index.
_CS_EXTS = (".cs",)


class ImportGraphBuilder:
    """Builds {source_path: set[target_path]} from staged files + transitive closure.

    Language-specific resolution lives behind the ImportResolver seam: one adapter per
    language (Python/TS/Go/C#), each returning a uniform ImportResult. The builder owns
    only the queue-driven closure and edge-line bookkeeping — it never parses imports
    itself, so adding a language is adding an adapter and one extension mapping.

    What:       resolves Python imports (import X.Y, from X.Y import Z), TypeScript/JS
                relative imports (import ... from './x', export ... from '../y'),
                Go imports (import "mod/pkg"), and C# usings (using X.Y) to on-disk
                paths, via the per-language ImportResolver adapters.
    Ignores:    stdlib/third-party and TS bare/aliased specifiers (unresolvable -> not in
                graph); Python relative imports and TS dynamic import() (deferred); Go
                test files as import targets (_test.go); C# usings of namespaces
                declared nowhere in the workspace (external assemblies).
    Basis:      AST_PY / AST_TS / AST_GO / AST_CSHARP via FileContextBuilder parse-once cache.
    shared_ctx: none (standalone builder; consumers may stash result under __import_graph__).
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str = ".",
                 max_files: int = 500, source_roots: dict[str, str] | None = None):
        self.builder = builder
        self.workspace = workspace
        self.max_files = max_files
        self.source_roots = source_roots or {}
        # {source_path: {resolved_target_path: import_line}} — consumers read
        # this (via shared_ctx["__import_lines__"]) to attribute a violation to
        # the exact import that produced the edge.
        self.import_lines: dict[str, dict[str, int]] = {}
        # ponytail: per-language resolvers, each built lazily on first file of its kind.
        self._resolvers: dict[str, ImportResolver] = {}

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
            if path in seen or not path.endswith((".py", ".go") + _TS_EXTS + _CS_EXTS):
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
        """Resolve a file's imports via its language adapter, recording import lines."""
        resolver = self._resolver_for(path)
        if resolver is None:
            return set()
        result = resolver.resolve(path)
        self.import_lines[path] = result.lines
        return result.targets

    def _resolver_for(self, path: str) -> "ImportResolver | None":
        """Return the ImportResolver for a file's language (built lazily), or None if unsupported."""
        if path.endswith(_TS_EXTS):
            return self._get_resolver("ts", self._make_ts_resolver)
        if path.endswith(".go"):
            return self._get_resolver("go", self._make_go_resolver)
        if path.endswith(_CS_EXTS):
            return self._get_resolver("cs", self._make_cs_resolver)
        if path.endswith(".py"):
            return self._get_resolver("py", self._make_py_resolver)
        return None

    def _get_resolver(self, key: str, factory) -> "ImportResolver":
        """Return the cached resolver for key, building it via factory on first use."""
        if key not in self._resolvers:
            self._resolvers[key] = factory()
        return self._resolvers[key]

    def _make_py_resolver(self) -> "ImportResolver":
        from enforcer.python_imports import PythonImportResolver
        return PythonImportResolver(self.builder, self.workspace, self.source_roots)

    def _make_ts_resolver(self) -> "ImportResolver":
        from enforcer.ts_imports import TsImportResolver
        return TsImportResolver(self.builder, self.workspace)

    def _make_go_resolver(self) -> "ImportResolver":
        from enforcer.go_imports import GoImportResolver
        return GoImportResolver(self.builder, self.workspace)

    def _make_cs_resolver(self) -> "ImportResolver":
        from enforcer.csharp_imports import CSharpNamespaceResolver
        return CSharpNamespaceResolver(self.builder, self.workspace)
