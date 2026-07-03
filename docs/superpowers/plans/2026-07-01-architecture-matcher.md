# ArchitectureMatcher + Facade Pattern Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ImportGraphBuilder`, `ArchitectureMatcher`, `FacadeExistsMatcher`, and `FacadeExposesInterfaceMatcher` to enforce layer dependencies and facade patterns at commit time.

**Architecture:** `ImportGraphBuilder` builds a directed import graph (staged files + transitive closure) into `shared_ctx["__import_graph__"]`. `ArchitectureMatcher` reads that graph and flags imports crossing forbidden layer boundaries. Facade matchers check existence and interface exposure per submodule. All are plain matchers composing with existing `Rule`/combinator infrastructure. Zero-cost when no `ArchitectureMatcher` is present (graph build gated on detection).

**Tech Stack:** Python 3.11+, tree-sitter (Python + TS ASTs), pytest, dataclasses, existing `enforcer` matcher/Rule/runner infrastructure.

---

## File Structure

New:
- `enforcer/import_graph.py` — `ImportGraphBuilder`: builds `{source_path: set[target_path]}` from staged files + transitive closure. Resolves `import X.Y` and `from X.Y import Z` to on-disk paths. Caches parses via `FileContextBuilder`.
- `enforcer/matchers/architecture.py` — `ArchitectureMatcher`: flags imports where `(source_layer, target_layer)` not in `allowed_edges` (or in `forbidden_edges`). Reads `__import_graph__` from `shared_ctx`.
- `enforcer/matchers/facade_exists.py` — `FacadeExistsMatcher`: flags directories matching `source_glob` that lack a `{facade}` file (e.g. `__init__.py`, `index.ts`).
- `enforcer/matchers/facade_exposes_interface.py` — `FacadeExposesInterfaceMatcher`: flags facade files with no `Protocol`/`ABC` (Python) or `interface` (TS) declaration or re-export.
- `tests/test_matchers/test_architecture.py` — paired tests for `ArchitectureMatcher`.
- `tests/test_matchers/test_facade_exists.py` — paired tests for `FacadeExistsMatcher`.
- `tests/test_matchers/test_facade_exposes_interface.py` — paired tests for `FacadeExposesInterfaceMatcher`.
- `tests/test_import_graph.py` — tests for `ImportGraphBuilder`.

Modified:
- `enforcer/matchers/__init__.py` — export `ArchitectureMatcher`, `FacadeExistsMatcher`, `FacadeExposesInterfaceMatcher`.
- `enforcer/check_runner.py` — `build_shared_ctx` gains `staged_files` param + conditional graph build.
- `enforcer/cli.py` — pass `staged_files` through to `build_shared_ctx` (one line per call site).
- `enforcer/mcp_server.py` — same pass-through.
- `enforcer_config.py` — add `arch-layer-deps` rule (Phase 1) + facade rules (Phase 2, for `enforcer/` submodules if applicable).

---

## Phase 1: Architecture Matcher

### Task 1: ImportGraphBuilder — resolve Python import paths

**Files:**
- Create: `enforcer/import_graph.py`
- Test: `tests/test_import_graph.py`

- [ ] **Step 1: Write failing test for single-file import resolution**

```python
# tests/test_import_graph.py
"""Tests for ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from pathlib import Path
import pytest
from enforcer.import_graph import ImportGraphBuilder
from enforcer.context import FileContextBuilder


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_single_file_imports_sibling(tmp_path: Path):
    """a.py imports b → graph has edge a → b."""
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    _write(tmp_path, "pkg/__init__.py", "")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert "pkg/a.py" in graph
    assert "pkg/b.py" in graph["pkg/a.py"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_import_graph.py::test_single_file_imports_sibling -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.import_graph'`

- [ ] **Step 3: Write minimal ImportGraphBuilder with path resolution**

```python
# enforcer/import_graph.py
"""ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enforcer.context import FileContextBuilder


class ImportGraphBuilder:
    """Builds {source_path: set[target_path]} from staged files + transitive closure.

    Resolves Python imports (import X.Y, from X.Y import Z) to on-disk paths.
    Reuses FileContextBuilder for parse-once caching. Skips stdlib/third-party
    (unresolvable → not in graph). Stops at closure (no new nodes).
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

        while queue and len(seen) < self.max_files:
            path = queue.pop(0)
            if path in seen or not path.endswith(".py"):
                continue
            seen.add(path)

            targets = self._extract_imports(path)
            resolved = set()
            for tgt in targets:
                resolved_paths = self._resolve_import(path, tgt)
                resolved.update(resolved_paths)
                for r in resolved_paths:
                    if r not in seen and r not in queue:
                        queue.append(r)
            graph[path] = resolved

        if len(seen) >= self.max_files:
            import sys
            sys.stderr.write(
                f"[enforcer] import graph cap ({self.max_files}) reached; "
                f"closure truncated. Staged files still fully checked.\n"
            )
        return graph

    def _extract_imports(self, path: str) -> set[str]:
        """Parse file's imports, return set of module-path strings. Cached."""
        if path in self._imports_cache:
            return self._imports_cache[path]
        from enforcer.types import Needs
        ctx = self.builder.build(path, force_needs={Needs.AST_PY})
        modules: set[str] = set()
        if not ctx.ast:
            self._imports_cache[path] = modules
            return modules
        from enforcer.parsers.ast_utils import walk_ast, node_text
        for node in walk_ast(ctx.ast.root_node):
            if node.type == "import_statement":
                # import X.Y → extract "X.Y"
                for child in node.children:
                    if child.type == "dotted_name":
                        modules.add(node_text(child))
            elif node.type == "import_from_statement":
                # from X.Y import Z → extract "X.Y" (first dotted_name)
                for child in node.children:
                    if child.type == "dotted_name":
                        modules.add(node_text(child))
                        break
        self._imports_cache[path] = modules
        return modules

    def _resolve_import(self, source_path: str, module: str) -> list[str]:
        """Resolve a dotted module string to on-disk paths relative to workspace.

        'pkg.sub' → ['pkg/sub/__init__.py', 'pkg/sub.py'] (whichever exists).
        Relative imports (module starts with '.') resolved against source package.
        """
        if not module or module.startswith("."):
            # ponytail: relative import support deferred — add when a repo needs it
            return []
        parts = module.split(".")
        candidates: list[str] = []

        # pkg/sub/__init__.py
        init_path = os.path.join(*parts, "__init__.py")
        candidates.append(init_path)
        # pkg/sub.py
        py_path = os.path.join(*parts[:-1], parts[-1] + ".py") if parts else ""
        if py_path:
            candidates.append(py_path)
        # top-level single: module.py
        if len(parts) == 1:
            candidates.append(parts[0] + ".py")

        resolved: list[str] = []
        for cand in candidates:
            full = os.path.join(self.workspace, cand)
            if os.path.isfile(full):
                resolved.append(cand.replace(os.sep, "/"))
        return resolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_import_graph.py::test_single_file_imports_sibling -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/import_graph.py tests/test_import_graph.py
git commit -m "feat(import-graph): add ImportGraphBuilder with Python path resolution"
```

---

### Task 2: ImportGraphBuilder — transitive closure test

**Files:**
- Modify: `tests/test_import_graph.py`

- [ ] **Step 1: Write failing test for transitive closure**

```python
def test_transitive_closure(tmp_path: Path):
    """a imports b, b imports c → graph has a→b, b→c, and a is expanded."""
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "from pkg import c\n")
    _write(tmp_path, "pkg/c.py", "x = 1\n")
    _write(tmp_path, "pkg/__init__.py", "")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert graph["pkg/a.py"] == {"pkg/b.py"}
    assert graph["pkg/b.py"] == {"pkg/c.py"}
    assert "pkg/c.py" in graph
    assert graph["pkg/c.py"] == set()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_import_graph.py::test_transitive_closure -v`
Expected: PASS (Task 1 implementation already handles transitive closure via queue)

- [ ] **Step 3: Commit**

```bash
git add tests/test_import_graph.py
git commit -m "test(import-graph): transitive closure across three files"
```

---

### Task 3: ImportGraphBuilder — stdlib/third-party skip + max_files cap

**Files:**
- Modify: `tests/test_import_graph.py`

- [ ] **Step 1: Write failing test for stdlib skip**

```python
def test_stdlib_not_in_graph(tmp_path: Path):
    """Unresolvable imports (stdlib) are not graph nodes."""
    _write(tmp_path, "pkg/a.py", "import os\nimport sys\nfrom pkg import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    _write(tmp_path, "pkg/__init__.py", "")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert graph["pkg/a.py"] == {"pkg/b.py"}
    assert "os" not in graph
    assert "sys" not in graph
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_import_graph.py::test_stdlib_not_in_graph -v`
Expected: PASS (stdlib unresolvable on disk → not added)

- [ ] **Step 3: Write failing test for max_files cap**

```python
def test_max_files_cap(tmp_path: Path, capsys):
    """Graph stops expanding at max_files, warns to stderr."""
    _write(tmp_path, "pkg/__init__.py", "")
    for i in range(5):
        _write(tmp_path, f"pkg/m{i}.py", f"from pkg import m{i + 1}\n" if i < 4 else "x = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path), max_files=3)
    graph = graph_builder.build(staged_files=["pkg/m0.py"])

    assert len(graph) <= 3
    captured = capsys.readouterr()
    assert "cap" in captured.err
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_import_graph.py::test_max_files_cap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_import_graph.py
git commit -m "test(import-graph): stdlib skip + max_files cap"
```

---

### Task 4: ImportGraphBuilder — negative parameterized tests

**Files:**
- Modify: `tests/test_import_graph.py`

- [ ] **Step 1: Write negative parameterized tests**

```python
@pytest.mark.parametrize("staged", [
    [],
    ["nonexistent.py"],
    ["pkg/empty.py"],
])
def test_no_imports_clean(tmp_path: Path, staged):
    """Empty staged list, missing files, or files with no imports → empty/trivial graph."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/empty.py", "x = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=staged)

    if not staged or staged == ["nonexistent.py"]:
        assert graph == {}
    else:
        assert graph.get("pkg/empty.py", set()) == set()


@pytest.mark.parametrize("source", [
    "x = 1\n",                           # no imports
    "import os\nimport sys\n",           # only stdlib
    "from pathlib import Path\n",        # only stdlib
])
def test_resolves_nothing_clean(tmp_path: Path, source):
    """Files with no resolvable imports produce empty target set."""
    _write(tmp_path, "pkg/a.py", source)
    _write(tmp_path, "pkg/__init__.py", "")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert graph["pkg/a.py"] == set()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_import_graph.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_import_graph.py
git commit -m "test(import-graph): negative parameterized cases"
```

---

### Task 5: ArchitectureMatcher — core find() with layer resolution

**Files:**
- Create: `enforcer/matchers/architecture.py`
- Test: `tests/test_matchers/test_architecture.py`

- [ ] **Step 1: Write failing test for forbidden edge detection**

```python
# tests/test_matchers/test_architecture.py
"""Tests for ArchitectureMatcher: flags imports crossing forbidden layer boundaries."""
import pytest
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.types import FileContext, Needs


def _ctx(path: str) -> FileContext:
    return FileContext(path=path, raw="# stub")


class TestArchitectureMatcherFlags:
    """flags imports where (source_layer, target_layer) is forbidden."""

    @pytest.mark.parametrize("src_path,tgt_path,expected_edge", [
        ("enforcer/matchers/foo.py", "enforcer/cli.py", "matchers -> io"),
        ("enforcer/runner.py", "enforcer/cli.py", "core -> io"),
        ("enforcer/types.py", "enforcer/runner.py", "types -> core"),
    ])
    def test_flags_forbidden_edge(self, src_path, tgt_path, expected_edge):
        layers = {
            "types": ["enforcer/types.py"],
            "core": ["enforcer/runner.py"],
            "matchers": ["enforcer/matchers/**/*.py"],
            "io": ["enforcer/cli.py"],
        }
        matcher = ArchitectureMatcher(
            layers=layers,
            allowed_edges=[("matchers", "types"), ("core", "types")],
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": {src_path: {tgt_path}}}
        matches = matcher.find(_ctx(src_path), shared_ctx)

        assert len(matches) == 1
        assert matches[0].matched_value == expected_edge
        assert matches[0].file == src_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_architecture.py::TestArchitectureMatcherFlags -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.matchers.architecture'`

- [ ] **Step 3: Write minimal ArchitectureMatcher**

```python
# enforcer/matchers/architecture.py
"""ArchitectureMatcher: flags imports crossing forbidden layer boundaries."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.rule import _glob_match


@dataclass
class ArchitectureMatcher:
    """Flags imports where (source_layer, target_layer) crosses forbidden boundaries.

    What:       flags import statements where source file's layer → target file's layer
                is not in allowed_edges (forbid_implicit=True) or is in forbidden_edges
    Ignores:    intra-layer imports; files not matching any layer glob; unresolvable targets
    Basis:      AST_PY (reads pre-built __import_graph__; line attribution walks AST)
    shared_ctx: reads __import_graph__ (dict[str, set[str]]) built by ImportGraphBuilder
    """
    layers: dict[str, list[str]] = field(default_factory=dict)
    allowed_edges: list[tuple[str, str]] = field(default_factory=list)
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    forbid_implicit: bool = True
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        # ponytail: precompute layer glob list for ordered lookup; first match wins
        self._layer_globs: list[tuple[str, list[str]]] = list(self.layers.items())

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag imports crossing forbidden layer boundaries. Returns list of Match."""
        shared_ctx = shared_ctx or {}
        graph = shared_ctx.get("__import_graph__", {})
        targets = graph.get(file_ctx.path, set())
        src_layer = self._layer_for_path(file_ctx.path)
        if src_layer is None:
            return []

        matches: list[Match] = []
        for tgt in targets:
            tgt_layer = self._layer_for_path(tgt)
            if tgt_layer is None:
                continue
            if tgt_layer == src_layer:
                continue
            edge = (src_layer, tgt_layer)
            if self._is_forbidden(edge):
                matches.append(Match(
                    file=file_ctx.path,
                    line=self._import_line_for(file_ctx, tgt),
                    matched_value=f"{src_layer} -> {tgt_layer}",
                ))
        return matches

    def _is_forbidden(self, edge: tuple[str, str]) -> bool:
        """Return True if edge is forbidden per allowed/forbidden config."""
        if self.forbid_implicit:
            return edge not in self.allowed_edges
        return edge in self.forbidden_edges

    def _layer_for_path(self, path: str) -> str | None:
        """Return layer name whose globs match path, or None."""
        for layer_name, globs in self._layer_globs:
            if any(_glob_match(path, g) for g in globs):
                return layer_name
        return None

    def _import_line_for(self, file_ctx: FileContext, target: str) -> int:
        """Walk file_ctx.ast for the import node resolving to target. Returns line or 0."""
        if not file_ctx.ast:
            return 0
        from enforcer.parsers.ast_utils import walk_ast, node_text
        target_module = target.replace("/", ".").removesuffix(".__init__").removesuffix(".py")
        for node in walk_ast(file_ctx.ast.root_node):
            if node.type not in ("import_statement", "import_from_statement"):
                continue
            text = node_text(node)
            # ponytail: substring match on the dotted path; precise resolution lives in ImportGraphBuilder
            if target_module in text or target.replace("/__init__.py", "").replace("/", ".") in text:
                return node.start_point[0] + 1
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matchers/test_architecture.py::TestArchitectureMatcherFlags -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/architecture.py tests/test_matchers/test_architecture.py
git commit -m "feat(matchers): add ArchitectureMatcher for layer-dependency enforcement"
```

---

### Task 6: ArchitectureMatcher — negative parameterized tests

**Files:**
- Modify: `tests/test_matchers/test_architecture.py`

- [ ] **Step 1: Write negative parameterized tests**

```python
class TestArchitectureMatcherClean:
    """does not flag allowed edges, intra-layer, or unlayered files."""

    @pytest.mark.parametrize("src_path,tgt_path", [
        ("enforcer/matchers/foo.py", "enforcer/types.py"),    # allowed edge
        ("enforcer/matchers/foo.py", "enforcer/matchers/bar.py"),  # intra-layer
        ("enforcer/runner.py", "enforcer/types.py"),           # allowed edge
    ])
    def test_no_match_on_allowed(self, src_path, tgt_path):
        layers = {
            "types": ["enforcer/types.py"],
            "core": ["enforcer/runner.py"],
            "matchers": ["enforcer/matchers/**/*.py"],
            "io": ["enforcer/cli.py"],
        }
        matcher = ArchitectureMatcher(
            layers=layers,
            allowed_edges=[("matchers", "types"), ("core", "types")],
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": {src_path: {tgt_path}}}
        matches = matcher.find(_ctx(src_path), shared_ctx)
        assert matches == []

    @pytest.mark.parametrize("src_path,tgt_path", [
        ("scripts/foo.py", "enforcer/types.py"),   # source not in any layer
        ("enforcer/types.py", "scripts/foo.py"),    # target not in any layer
    ])
    def test_no_match_unlayered(self, src_path, tgt_path):
        matcher = ArchitectureMatcher(
            layers={"types": ["enforcer/types.py"]},
            allowed_edges=[],
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": {src_path: {tgt_path}}}
        assert matcher.find(_ctx(src_path), shared_ctx) == []

    def test_no_graph_returns_empty(self):
        matcher = ArchitectureMatcher(layers={"a": ["a.py"]}, forbid_implicit=True)
        assert matcher.find(_ctx("a.py"), shared_ctx={}) == []

    def test_forbid_implicit_false_uses_forbidden_edges(self):
        layers = {"a": ["a.py"], "b": ["b.py"]}
        matcher = ArchitectureMatcher(
            layers=layers,
            forbidden_edges=[("a", "b")],
            forbid_implicit=False,
        )
        shared_ctx = {"__import_graph__": {"a.py": {"b.py"}}}
        matches = matcher.find(_ctx("a.py"), shared_ctx)
        assert len(matches) == 1
        assert matches[0].matched_value == "a -> b"

    def test_needs_ast_py(self):
        assert ArchitectureMatcher(layers={}).needs == Needs.AST_PY
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_architecture.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_matchers/test_architecture.py
git commit -m "test(matchers): ArchitectureMatcher negative parameterized cases"
```

---

### Task 7: Export ArchitectureMatcher + wire into check_runner

**Files:**
- Modify: `enforcer/matchers/__init__.py`
- Modify: `enforcer/check_runner.py`
- Modify: `enforcer/cli.py`
- Modify: `enforcer/mcp_server.py`

- [ ] **Step 1: Export ArchitectureMatcher**

```python
# enforcer/matchers/__init__.py — add import and __all__ entry
from enforcer.matchers.architecture import ArchitectureMatcher
# ... in __all__ list, add:
#     "ArchitectureMatcher",
```

- [ ] **Step 2: Add `_has_architecture_matcher` to check_runner.py**

Add this function and modify `build_shared_ctx`:

```python
# enforcer/check_runner.py — add after _glob_any_match
def _has_architecture_matcher(rules: list) -> bool:
    """Return True if any rule contains an ArchitectureMatcher in its matcher tree."""
    stack: list = []
    for rule in rules:
        stack.extend(rule.matchers)
    while stack:
        m = stack.pop()
        if hasattr(m, "layers"):
            return True
        if hasattr(m, "matchers") and isinstance(m.matchers, list):
            stack.extend(m.matchers)
        elif hasattr(m, "matcher") and m.matcher is not None:
            stack.append(m.matcher)
    return False


# Modify build_shared_ctx signature and body:
def build_shared_ctx(config, builder, ws: str, staged_files: list[str] | None = None) -> dict:
    """Build shared context dict from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:
                    shared_ctx[rel] = builder.build(rel)

    if staged_files and _has_architecture_matcher(config.rules):
        from enforcer.import_graph import ImportGraphBuilder
        graph_builder = ImportGraphBuilder(builder=builder, workspace=ws)
        shared_ctx["__import_graph__"] = graph_builder.build(staged_files)

    return shared_ctx
```

- [ ] **Step 3: Pass staged_files through in cli.py**

Find every call to `build_shared_ctx` in `enforcer/cli.py` and add `staged_files=file_list`. Example:

```python
shared_ctx = build_shared_ctx(config, builder, ws, staged_files=file_list)
```

Use `grep` to find all call sites: `grep -n "build_shared_ctx" enforcer/cli.py`

- [ ] **Step 4: Pass staged_files through in mcp_server.py**

Find every call to `build_shared_ctx` in `enforcer/mcp_server.py` and add `staged_files=file_list`.

Use `grep` to find all call sites: `grep -n "build_shared_ctx" enforcer/mcp_server.py`

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `pytest --tb=short -q`
Expected: PASS (all existing tests still green; new export doesn't break anything)

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/__init__.py enforcer/check_runner.py enforcer/cli.py enforcer/mcp_server.py
git commit -m "feat(check-runner): wire ImportGraphBuilder into shared_ctx for ArchitectureMatcher"
```

---

### Task 8: Add arch-layer-deps rule to enforcer_config.py

**Files:**
- Modify: `enforcer_config.py`

- [ ] **Step 1: Add the rule**

Add to the imports section:

```python
from enforcer.matchers import ArchitectureMatcher
```

Add to the `RULES` list:

```python
Rule(
    id="arch-layer-deps",
    severity=Severity.ERROR,
    matchers=[ArchitectureMatcher(
        layers={
            "types":      ["enforcer/types.py"],
            "rule":       ["enforcer/rule.py"],
            "core":       ["enforcer/runner.py", "enforcer/context.py",
                           "enforcer/config.py", "enforcer/check_runner.py"],
            "matchers":   ["enforcer/matchers/**/*.py"],
            "predicates": ["enforcer/predicates/**/*.py"],
            "combinators":["enforcer/combinators/**/*.py"],
            "extractors": ["enforcer/extractors/**/*.py"],
            "parsers":    ["enforcer/parsers/**/*.py"],
            "io":         ["enforcer/cli.py", "enforcer/mcp_server.py",
                           "enforcer/reporter.py", "enforcer/docs.py",
                           "enforcer/explain.py", "enforcer/fix.py",
                           "enforcer/ignore.py", "enforcer/llm.py"],
        },
        allowed_edges=[
            ("matchers", "types"),
            ("matchers", "parsers"),
            ("predicates", "types"),
            ("combinators", "types"),
            ("combinators", "matchers"),
            ("extractors", "types"),
            ("core", "types"),
            ("core", "rule"),
            ("core", "parsers"),
            ("core", "matchers"),
            ("core", "combinators"),
            ("core", "extractors"),
            ("io", "types"),
            ("io", "rule"),
            ("io", "core"),
            ("io", "parsers"),
            ("io", "matchers"),
            ("io", "combinators"),
            ("io", "extractors"),
            ("parsers", "types"),
        ],
        forbid_implicit=True,
    )],
    file_globs=["enforcer/**/*.py"],
    exclude_globs=["enforcer/__init__.py"],
    diff_only=False,
    message="Layer violation: {matched_value} at {file}:{line}",
    fix_instruction="Move shared logic down to a lower layer, or add the edge to allowed_edges if intentional.",
    rationale="Importing upward creates circular deps and prevents isolated testing. Layers: types < rule/parsers/matchers/predicates/combinators/extractors < core < io.",
),
```

- [ ] **Step 2: Regenerate CONVENTIONS.md**

Run: `enforcer sync-doc`
Expected: CONVENTIONS.md updated with the new `arch-layer-deps` rule.

- [ ] **Step 3: Run enforcer on this repo — must pass**

Run: `enforcer check --staged`
Expected: No architecture violations (the repo's current imports comply with the declared layers). If violations appear, fix the `allowed_edges` or the offending import.

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer_config.py CONVENTIONS.md
git commit -m "feat(config): add arch-layer-deps rule for self-enforcement"
```

---

## Phase 2: Facade Pattern Rules

### Task 9: FacadeExistsMatcher — flags directories missing a facade file

**Files:**
- Create: `enforcer/matchers/facade_exists.py`
- Test: `tests/test_matchers/test_facade_exists.py`

- [ ] **Step 1: Write failing test for missing facade**

```python
# tests/test_matchers/test_facade_exists.py
"""Tests for FacadeExistsMatcher: flags directories matching source_glob missing a facade file."""
import pytest
from enforcer.matchers.facade_exists import FacadeExistsMatcher
from enforcer.types import FileContext, Needs


class TestFacadeExistsFlags:
    """flags directories missing a facade file."""

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts"])
    def test_flags_missing_facade(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "foo.ts").write_text("x = 1\n")

        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert facade in matches[0].matched_value

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts"])
    def test_flags_missing_facade_empty_dir(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        matches = matcher.find(ctx)
        assert len(matches) == 1


class TestFacadeExistsClean:
    """does not flag when facade exists or dir doesn't match."""

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts"])
    def test_clean_when_facade_exists(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / facade).write_text("export = 1\n")

        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        assert matcher.find(ctx) == []

    def test_clean_non_matching_dir(self, tmp_path):
        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade="__init__.py",
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="other/foo.py", raw="x = 1\n")
        assert matcher.find(ctx) == []

    def test_needs_raw(self):
        assert FacadeExistsMatcher(source_glob="*", facade="x").needs == Needs.RAW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_facade_exists.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.matchers.facade_exists'`

- [ ] **Step 3: Write minimal FacadeExistsMatcher**

```python
# enforcer/matchers/facade_exists.py
"""FacadeExistsMatcher: flags directories matching source_glob that lack a facade file."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.rule import _glob_match


@dataclass
class FacadeExistsMatcher:
    """Flags directories matching source_glob that are missing the facade file.

    What:       flags files whose parent directory matches source_glob but lacks {facade}
    Ignores:    files whose parent dir doesn't match source_glob; dirs with facade present
    Basis:      RAW (pathlib.Path checks on workspace)
    shared_ctx: none
    """
    source_glob: str
    facade: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag if file's parent dir matches source_glob and lacks facade. Returns list of Match."""
        parent = os.path.dirname(file_ctx.path)
        if not _glob_match(parent + "/", self.source_glob + "/"):
            # ponytail: also try matching parent directly (source_glob may or may not end with /)
            if not _glob_match(parent, self.source_glob):
                return []
        facade_path = os.path.join(self.workspace, parent, self.facade)
        if os.path.isfile(facade_path):
            return []
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=f"{parent}/{self.facade} missing",
        )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_facade_exists.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/facade_exists.py tests/test_matchers/test_facade_exists.py
git commit -m "feat(matchers): add FacadeExistsMatcher for facade file existence checks"
```

---

### Task 10: FacadeExposesInterfaceMatcher — flags facades without interface

**Files:**
- Create: `enforcer/matchers/facade_exposes_interface.py`
- Test: `tests/test_matchers/test_facade_exposes_interface.py`

- [ ] **Step 1: Write failing test for missing interface**

```python
# tests/test_matchers/test_facade_exposes_interface.py
"""Tests for FacadeExposesInterfaceMatcher: flags facade files with no interface declaration."""
import pytest
from enforcer.matchers.facade_exposes_interface import FacadeExposesInterfaceMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "__init__.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_PROTOCOL = '''\
from typing import Protocol

class Repo(Protocol):
    def find(self, id: int) -> dict: ...
'''

_ABC = '''\
from abc import ABC

class Repo(ABC):
    def find(self, id: int) -> dict: ...
    pass
'''

_IMPL_ONLY = '''\
class RepoImpl:
    def find(self, id: int) -> dict:
        return {}
'''

_EMPTY = "x = 1\n"

_REEXPORT = '''\
from .repo import Repo  # Protocol defined in repo.py, re-exported here
__all__ = ["Repo"]
'''


class TestFacadeExposesInterfaceFlags:
    """flags facade files with no Protocol/ABC/interface."""

    @pytest.mark.parametrize("source", [_IMPL_ONLY, _EMPTY])
    def test_flags_no_interface(self, source):
        ctx = _make_ctx(source)
        matcher = FacadeExposesInterfaceMatcher()
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert "no interface" in matches[0].matched_value


class TestFacadeExposesInterfaceClean:
    """does not flag facades with Protocol/ABC or valid re-export."""

    @pytest.mark.parametrize("source", [_PROTOCOL, _ABC])
    def test_clean_with_interface(self, source):
        ctx = _make_ctx(source)
        matcher = FacadeExposesInterfaceMatcher()
        assert matcher.find(ctx) == []

    def test_clean_with_reexport(self):
        # ponytail: re-export detection — __all__ referencing a Protocol name
        # This is a heuristic; precise type-checking of re-exported names is deferred.
        ctx = _make_ctx(_REEXPORT)
        matcher = FacadeExposesInterfaceMatcher()
        # Re-export alone (without __all__ type info) may still flag — that's acceptable
        # for v1. If __all__ is present and non-empty, consider it "exposes something."
        assert matcher.find(ctx) == []

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="__init__.py", raw="x = 1\n")
        assert FacadeExposesInterfaceMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert FacadeExposesInterfaceMatcher().needs == Needs.AST_PY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_facade_exposes_interface.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'enforcer.matchers.facade_exposes_interface'`

- [ ] **Step 3: Write minimal FacadeExposesInterfaceMatcher**

```python
# enforcer/matchers/facade_exposes_interface.py
"""FacadeExposesInterfaceMatcher: flags facade files with no Protocol/ABC interface declaration."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text


@dataclass
class FacadeExposesInterfaceMatcher:
    """Flags facade files that don't expose a public interface (Protocol/ABC in Python).

    What:       flags files with no class(Protocol) or class(ABC) declaration,
                and no non-empty __all__ re-export
    Ignores:    files with no parsed AST; files with a Protocol/ABC class; files with __all__
    Basis:      AST_PY (walks file_ctx.ast for class_definition with Protocol/ABC bases)
    shared_ctx: none
    """
    interface_bases: tuple[str, ...] = ("Protocol", "ABC")
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag if no interface declaration found. Returns list of Match."""
        if not file_ctx.ast:
            return []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if self._is_interface_decl(node):
                return []
            if self._is_reexport_all(node):
                return []
        return [Match(
            file=file_ctx.path,
            line=1,
            matched_value="no interface exposed",
        )]

    def _is_interface_decl(self, node) -> bool:
        """Return True if node is a class_definition with an interface base (Protocol/ABC)."""
        if node.type != "class_definition":
            return False
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        name = node_text(arg)
                        if name in self.interface_bases:
                            return True
        return False

    def _is_reexport_all(self, node) -> bool:
        """Return True if node is a non-empty __all__ assignment (heuristic re-export)."""
        # ponytail: heuristic — __all__ = [...] presence means "this is a facade with public API"
        if node.type != "assignment":
            return False
        left = node.child_by_field_name("left")
        if not left or node_text(left) != "__all__":
            return False
        right = node.child_by_field_name("right")
        if not right:
            return False
        # non-empty list/tuple
        text = node_text(right)
        return bool(text.strip("[]() \n\t"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_facade_exposes_interface.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/matchers/facade_exposes_interface.py tests/test_matchers/test_facade_exposes_interface.py
git commit -m "feat(matchers): add FacadeExposesInterfaceMatcher for facade interface checks"
```

---

### Task 11: Export facade matchers + add facade rules to config

**Files:**
- Modify: `enforcer/matchers/__init__.py`
- Modify: `enforcer_config.py`

- [ ] **Step 1: Export facade matchers**

```python
# enforcer/matchers/__init__.py — add imports and __all__ entries
from enforcer.matchers.facade_exists import FacadeExistsMatcher
from enforcer.matchers.facade_exposes_interface import FacadeExposesInterfaceMatcher
# ... in __all__ list, add:
#     "FacadeExistsMatcher",
#     "FacadeExposesInterfaceMatcher",
```

- [ ] **Step 2: Add facade rules to enforcer_config.py**

Add imports:

```python
from enforcer.matchers import FacadeExposesInterfaceMatcher
```

Add rules to `RULES` (only if `enforcer/` submodules have `__init__.py` facades — verify first; if they don't, skip or add facades):

```python
# Only add if enforcer/ submodules actually use __init__.py as facades.
# If they don't, these rules are documentation of intent, not self-enforcement.
# Comment out or gate behind a flag if the repo doesn't follow the pattern yet.
```

Note: the `enforcer/` package uses `__init__.py` for exports (e.g., `enforcer/matchers/__init__.py`). Check whether each submodule's `__init__.py` re-exports or declares an interface. If they're just empty namespace markers, the facade rules would flag them — that's correct behavior (tells you to add a proper facade or interface). But adding rules that fail on the current repo blocks all commits. Decision: add the rules but set `severity=Severity.WARN` initially, so they remind without blocking, until the facades are properly written.

- [ ] **Step 3: Regenerate CONVENTIONS.md**

Run: `enforcer sync-doc`
Expected: CONVENTIONS.md updated.

- [ ] **Step 4: Run enforcer on this repo**

Run: `enforcer check --staged`
Expected: If WARN rules fire, acknowledge with `ENFORCER_CONFIRM_WARNINGS=1` or fix the facades. If ERROR rules fire, either fix or downgrade to WARN.

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/__init__.py enforcer_config.py CONVENTIONS.md
git commit -m "feat(config): add facade pattern rules (WARN until facades complete)"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 2: Run enforcer self-check**

Run: `enforcer check --staged --confirm-read-warnings`
Expected: No violations (or only acknowledged WARNs).

- [ ] **Step 3: Verify CONVENTIONS.md is in sync**

Run: `enforcer sync-doc --output /tmp/conventions_check.md && diff CONVENTIONS.md /tmp/conventions_check.md`
Expected: No diff (in sync).

- [ ] **Step 4: Commit any final sync**

```bash
git add CONVENTIONS.md
git commit -m "docs: sync CONVENTIONS.md" --allow-empty
```
