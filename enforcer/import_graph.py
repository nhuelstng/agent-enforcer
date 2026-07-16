"""ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from __future__ import annotations
import os
import sys
from abc import ABC
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder

# TypeScript/JS files the graph traverses, and the order relative specifiers
# resolve against (a bare 'foo' import tries foo.ts, then foo.tsx, ...).
_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_TS_RESOLVE_EXTS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mts", ".cts")


class ImportGraphBuilder(ABC):
    """Builds {source_path: set[target_path]} from staged files + transitive closure.

    What:       resolves Python imports (import X.Y, from X.Y import Z), TypeScript/JS
                relative imports (import ... from './x', export ... from '../y'), and
                Go imports (import "mod/pkg") to on-disk paths. A Go import resolves to
                every .go file in the target package directory (a Go package is a dir).
    Ignores:    stdlib/third-party and TS bare/aliased specifiers (unresolvable -> not in
                graph); Python relative imports and TS dynamic import() (deferred); Go
                test files as import targets (_test.go).
    Basis:      AST_PY / AST_TS / AST_GO via FileContextBuilder parse-once cache.
    shared_ctx: none (standalone builder; consumers may stash result under __import_graph__).
    """

    def __init__(self, builder: "FileContextBuilder", workspace: str = ".",
                 max_files: int = 500, source_roots: dict[str, str] | None = None):
        self.builder = builder
        self.workspace = workspace
        self.max_files = max_files
        # ponytail: import-prefix -> on-disk dir, for a package rooted in a
        # subdirectory (import 'app.x' whose file lives at 'server/app/x.py').
        # Longest prefix first so 'app.sub' wins over 'app'.
        self.source_roots = dict(
            sorted((source_roots or {}).items(), key=lambda kv: -len(kv[0]))
        )
        # ponytail: parse-once cache keyed by path. Python/TS entries map each
        # import to the 1-based line of its statement (line attribution recorded
        # at resolution time); Go entries hold the bare import-path set (Go line
        # attribution is resolved lazily by consumers via ast_utils).
        self._imports_cache: dict[str, dict[str, int] | set[str]] = {}
        # {source_path: {resolved_target_path: import_line}} — consumers read
        # this (via shared_ctx["__import_lines__"]) to attribute a violation to
        # the exact import that produced the edge.
        self.import_lines: dict[str, dict[str, int]] = {}
        # ponytail: Go module path from go.mod, resolved lazily. False = not yet
        # read; None = no go.mod / no module line; str = the module path.
        self._go_module: str | None | bool = False

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
            if path in seen or not path.endswith((".py", ".go") + _TS_EXTS):
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
        """Extract imports for path, resolve to target paths, record import lines."""
        if path.endswith(_TS_EXTS):
            return self._resolve_ts_for_path(path)
        if path.endswith(".go"):
            return self._resolve_go_for_path(path)
        resolved: set[str] = set()
        lines: dict[str, int] = {}
        for module, line in self._extract_imports(path).items():
            for target in self._resolve_import(module):
                resolved.add(target)
                lines.setdefault(target, line)
        self.import_lines[path] = lines
        return resolved

    def _extract_imports(self, path: str) -> dict[str, int]:
        """Parse file's imports, return {dotted module-path: 1-based line}. Cached.

        Emits 'X.Y.Z' for 'from X.Y import Z' (Z may be symbol or submodule).
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
                ImportGraphBuilder._collect_plain_import(node, node_text, modules, line)
            elif node.type == "import_from_statement":
                ImportGraphBuilder._collect_from_import(node, node_text, modules, line)

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
            name = ImportGraphBuilder._dotted_name_text(child, node_text)
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
            name = ImportGraphBuilder._dotted_name_text(name_node, node_text)
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

    # --- TypeScript / JS resolution ---
    # Only relative specifiers ('./', '../') are local; bare ('rxjs') and aliased
    # ('@angular/core', tsconfig paths) specifiers resolve to nothing, like an
    # unresolvable Python module. A specifier resolves to the first on-disk file
    # among <base><ext> then <base>/index<ext> (TS module-resolution order).

    def _resolve_ts_for_path(self, path: str) -> set[str]:
        """Resolve a TS/JS file's relative imports, recording each import's line."""
        resolved: set[str] = set()
        lines: dict[str, int] = {}
        for spec, line in self._extract_ts_imports(path).items():
            target = self._resolve_ts_import(spec, path)
            if target is not None:
                resolved.add(target)
                lines.setdefault(target, line)
        self.import_lines[path] = lines
        return resolved

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

    # --- Go resolution ---
    # A Go package is a directory; an import path resolves (against the go.mod
    # module prefix) to every non-test .go file in that directory.

    def _resolve_go_for_path(self, path: str) -> set[str]:
        """Resolve a Go file's local imports to the .go files of each target package."""
        module = self._go_module_path()
        if not module:
            return set()
        resolved: set[str] = set()
        for imp in self._extract_go_imports(path):
            resolved.update(self._resolve_go_import(imp, module))
        return resolved

    def _extract_go_imports(self, path: str) -> set[str]:
        """Return the set of import-path strings declared in a Go file. Cached."""
        if path in self._imports_cache:
            return self._imports_cache[path]
        from enforcer.types import Needs
        ctx = self.builder.build(path, force_needs={Needs.AST_GO})
        imports = self._go_import_strings(ctx.ast.root_node) if ctx.ast else set()
        self._imports_cache[path] = imports
        return imports

    @staticmethod
    def _go_import_strings(root) -> set[str]:
        """Collect the quoted path from every Go import_spec node under root."""
        from enforcer.parsers.ast_utils import walk_ast, node_text
        imports: set[str] = set()
        for node in walk_ast(root):
            if node.type != "import_spec":
                continue
            literal = next((c for c in node.children
                            if c.type in ("interpreted_string_literal", "raw_string_literal")), None)
            if literal is not None:
                imports.add(node_text(literal).strip('"`'))
        return imports

    def _resolve_go_import(self, import_path: str, module: str) -> list[str]:
        """Map a local import path to the non-test .go files in its package directory.

        Only imports under the module prefix are local; stdlib/third-party imports
        resolve to nothing (like unresolvable Python modules).
        """
        if import_path == module:
            rel = ""
        elif import_path.startswith(module + "/"):
            rel = import_path[len(module) + 1:]
        else:
            return []
        pkg_dir = os.path.join(self.workspace, rel) if rel else self.workspace
        if not os.path.isdir(pkg_dir):
            return []
        files: list[str] = []
        for name in os.listdir(pkg_dir):
            if not name.endswith(".go") or name.endswith("_test.go"):
                continue
            if not os.path.isfile(os.path.join(pkg_dir, name)):
                continue
            files.append(f"{rel}/{name}" if rel else name)
        return files

    def _go_module_path(self) -> str | None:
        """Return the module path from go.mod at the workspace root, or None. Cached."""
        if self._go_module is not False:
            return self._go_module  # type: ignore[return-value]
        self._go_module = self._parse_go_mod(os.path.join(self.workspace, "go.mod"))
        return self._go_module

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
