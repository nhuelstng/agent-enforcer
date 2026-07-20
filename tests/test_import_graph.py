"""Tests for ImportGraphBuilder: builds directed import graph from staged files + transitive closure."""
from pathlib import Path
import pytest
from enforcer.import_graph import ImportGraphBuilder
from enforcer.context import FileContextBuilder
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.types import FileContext


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_single_file_imports_sibling(tmp_path: Path):
    """a.py imports b -> graph has edge a -> b."""
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    _write(tmp_path, "pkg/__init__.py", "")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert "pkg/a.py" in graph
    assert "pkg/b.py" in graph["pkg/a.py"]


def test_transitive_closure(tmp_path: Path):
    """a imports b, b imports c -> graph has a->b, b->c, and a is expanded."""
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


@pytest.mark.parametrize("staged", [
    [],
    ["nonexistent.py"],
    ["pkg/empty.py"],
])
def test_no_imports_clean(tmp_path: Path, staged):
    """Empty staged list, missing files, or files with no imports -> empty/trivial graph."""
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


@pytest.mark.parametrize("source,expected", [
    ("from pkg import b as foo\n", {"pkg/b.py"}),
    ("from pkg import b as foo, c\n", {"pkg/b.py", "pkg/c.py"}),
    ("import pkg.b, pkg.c\n", {"pkg/b.py", "pkg/c.py"}),
    ("import os as o, sys as s\n", set()),
    ("from pkg import b as foo\nfrom pkg import c as bar\n", {"pkg/b.py", "pkg/c.py"}),
])
def test_aliased_and_multimodule_imports(tmp_path: Path, source, expected):
    """Aliased from-imports and multi-module plain imports resolve correctly."""
    _write(tmp_path, "pkg/a.py", source)
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    _write(tmp_path, "pkg/c.py", "x = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert graph["pkg/a.py"] == expected


@pytest.mark.parametrize("source,expected", [
    ("from enforcer.types import Needs\n", {"enforcer/types.py"}),
    ("from enforcer.matchers import RegexMatcher\n", {"enforcer/matchers/__init__.py"}),
    ("from enforcer.parsers.ast_utils import walk_ast\n", {"enforcer/parsers/ast_utils.py"}),
])
def test_from_import_symbol_falls_back_to_package(tmp_path: Path, source, expected):
    """from X.Y import Z where Z is a symbol (not submodule) resolves to X.Y's file."""
    for rel in [
        "enforcer/__init__.py", "enforcer/types.py",
        "enforcer/matchers/__init__.py",
        "enforcer/parsers/__init__.py", "enforcer/parsers/ast_utils.py",
    ]:
        _write(tmp_path, rel, "x = 1\n")
    _write(tmp_path, "enforcer/runner.py", source)

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["enforcer/runner.py"])

    assert graph["enforcer/runner.py"] == expected


def test_end_to_end_architecture_violation(tmp_path: Path):
    """from X import Y must resolve to X's file, and ArchitectureMatcher flags the edge."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from pkg import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["pkg/a.py"])

    assert graph["pkg/a.py"] == {"pkg/b.py"}

    matcher = ArchitectureMatcher(
        layers={
            "a_layer": ["pkg/a.py"],
            "b_layer": ["pkg/b.py"],
        },
        forbidden_edges=[("a_layer", "b_layer")],
        forbid_implicit=False,
    )
    ctx = FileContext(path="pkg/a.py", raw="from pkg import b\n")
    matches = matcher.find(ctx, {"__import_graph__": graph})
    assert len(matches) == 1
    assert matches[0].matched_value == "a_layer -> b_layer"


def test_source_root_resolves_subdir_package(tmp_path: Path):
    """A package imported as 'app.*' but rooted at 'server/app' resolves via source_roots."""
    _write(tmp_path, "server/app/features/a/x.py", "from app.features.b.y import z\n")
    _write(tmp_path, "server/app/features/b/y.py", "z = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path), source_roots={"app": "server/app"},
    )
    graph = graph_builder.build(staged_files=["server/app/features/a/x.py"])

    assert graph["server/app/features/a/x.py"] == {"server/app/features/b/y.py"}


def test_without_source_root_subdir_package_unresolved(tmp_path: Path):
    """Same layout, no source_roots -> 'app.*' does not resolve (regression guard)."""
    _write(tmp_path, "server/app/features/a/x.py", "from app.features.b.y import z\n")
    _write(tmp_path, "server/app/features/b/y.py", "z = 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["server/app/features/a/x.py"])

    assert graph["server/app/features/a/x.py"] == set()


def test_source_root_symbol_fallback(tmp_path: Path):
    """'from app.mod import symbol' falls back to the parent module file under the source root."""
    _write(tmp_path, "server/app/mod.py", "symbol = 1\n")
    _write(tmp_path, "server/app/caller.py", "from app.mod import symbol\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path), source_roots={"app": "server/app"},
    )
    graph = graph_builder.build(staged_files=["server/app/caller.py"])

    assert graph["server/app/caller.py"] == {"server/app/mod.py"}


def test_source_root_longest_prefix_wins(tmp_path: Path):
    """When two prefixes overlap, the longer dotted prefix maps first."""
    _write(tmp_path, "vendored/sub/thing.py", "v = 1\n")
    _write(tmp_path, "server/app/thing.py", "a = 1\n")
    _write(tmp_path, "server/app/caller.py", "from app.sub.thing import v\nfrom app.thing import a\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path),
        source_roots={"app": "server/app", "app.sub": "vendored/sub"},
    )
    graph = graph_builder.build(staged_files=["server/app/caller.py"])

    assert graph["server/app/caller.py"] == {"vendored/sub/thing.py", "server/app/thing.py"}


def test_source_root_enables_sibling_isolation_at_repo_root(tmp_path: Path):
    """End-to-end: source_roots lets isolate_siblings fire for a subdir-rooted package."""
    _write(tmp_path, "server/app/features/orders/svc.py", "from app.features.billing.pay import charge\n")
    _write(tmp_path, "server/app/features/billing/pay.py", "def charge():\n    return 1\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path), source_roots={"app": "server/app"},
    )
    graph = graph_builder.build(staged_files=["server/app/features/orders/svc.py"])

    matcher = ArchitectureMatcher(isolate_siblings=["server/app/features"])
    ctx = FileContext(path="server/app/features/orders/svc.py", raw="from app.features.billing.pay import charge\n")
    matches = matcher.find(ctx, {"__import_graph__": graph})
    assert len(matches) == 1
    assert "sibling slices" in matches[0].matched_value


def test_import_lines_recorded(tmp_path: Path):
    """The builder records the 1-based line of each resolving import."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    _write(tmp_path, "pkg/a.py", "import os\n\nfrom pkg import b\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    gb.build(staged_files=["pkg/a.py"])

    assert gb.import_lines["pkg/a.py"]["pkg/b.py"] == 3


def test_import_lines_recorded_via_source_root(tmp_path: Path):
    """Line attribution follows the SOURCE_ROOTS remap (import name != on-disk path)."""
    _write(tmp_path, "server/app/features/billing/pay.py", "def charge():\n    return 1\n")
    _write(tmp_path, "server/app/features/orders/svc.py",
           "import json\n\n\nfrom app.features.billing.pay import charge\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path), source_roots={"app": "server/app"},
    )
    gb.build(staged_files=["server/app/features/orders/svc.py"])

    # the import sits on line 4, though written as 'app.…' not 'server/app/…'
    assert gb.import_lines["server/app/features/orders/svc.py"]["server/app/features/billing/pay.py"] == 4


def test_architecture_matcher_uses_recorded_line(tmp_path: Path):
    """End-to-end: a source-root sibling violation reports the real import line, not 0."""
    _write(tmp_path, "server/app/features/billing/pay.py", "def charge():\n    return 1\n")
    src = "server/app/features/orders/svc.py"
    _write(tmp_path, src, "import json\n\n\nfrom app.features.billing.pay import charge\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(
        builder=builder, workspace=str(tmp_path), source_roots={"app": "server/app"},
    )
    graph = gb.build(staged_files=[src])
    shared_ctx = {"__import_graph__": graph, "__import_lines__": gb.import_lines}

    matcher = ArchitectureMatcher(isolate_siblings=["server/app/features"])
    ctx = builder.build(src)
    matches = matcher.find(ctx, shared_ctx)
    assert len(matches) == 1
    assert matches[0].line == 4          # was 0 before recorded-line attribution
    assert "sibling slices" in matches[0].matched_value


def _ts_available() -> bool:
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    return parse("const x = 1;\n", Needs.AST_TS) is not None


ts_only = pytest.mark.skipif(not _ts_available(), reason="tree-sitter TypeScript grammar not available")


@ts_only
def test_ts_relative_import_resolves(tmp_path: Path):
    """A relative TS import resolves to the sibling on-disk file."""
    _write(tmp_path, "src/features/billing/pay.ts", "export const pay = 1;\n")
    _write(tmp_path, "src/features/orders/svc.ts", "import { pay } from '../billing/pay';\nexport const x = pay;\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=["src/features/orders/svc.ts"])

    assert graph["src/features/orders/svc.ts"] == {"src/features/billing/pay.ts"}
    assert gb.import_lines["src/features/orders/svc.ts"]["src/features/billing/pay.ts"] == 1


@ts_only
def test_ts_barrel_index_and_reexport(tmp_path: Path):
    """A directory specifier resolves to index.ts; `export … from` counts as an edge."""
    _write(tmp_path, "src/shared/ui/badge.component.ts", "export const Badge = 1;\n")
    _write(tmp_path, "src/shared/ui/index.ts", "export { Badge } from './badge.component';\n")
    _write(tmp_path, "src/app/host.ts", "import { Badge } from '../shared/ui';\nexport const b = Badge;\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=["src/app/host.ts"])

    assert "src/shared/ui/index.ts" in graph["src/app/host.ts"]              # dir -> index.ts
    assert graph["src/shared/ui/index.ts"] == {"src/shared/ui/badge.component.ts"}  # re-export edge


@ts_only
def test_ts_bare_and_aliased_specifiers_unresolved(tmp_path: Path):
    """Bare (npm) and non-relative specifiers resolve to nothing."""
    _write(tmp_path, "src/a.ts", "import { Component } from '@angular/core';\nimport { of } from 'rxjs';\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=["src/a.ts"])

    assert graph["src/a.ts"] == set()


@ts_only
def test_ts_sibling_isolation_end_to_end(tmp_path: Path):
    """ArchitectureMatcher flags a cross-slice TS import at the correct line."""
    _write(tmp_path, "src/features/billing/pay.ts", "export const pay = 1;\n")
    src = "src/features/orders/svc.ts"
    _write(tmp_path, src, "import { Component } from '@angular/core';\n\nimport { pay } from '../billing/pay';\n")

    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=[src])
    shared_ctx = {"__import_graph__": graph, "__import_lines__": gb.import_lines}

    matcher = ArchitectureMatcher(isolate_siblings=["src/features"])
    matches = matcher.find(builder.build(src), shared_ctx)
    assert len(matches) == 1
    assert matches[0].line == 3
    assert "sibling slices" in matches[0].matched_value


# --- Go import graph ---

_GOMOD = "module example.com/proj\n\ngo 1.22\n"


def _go_builder(tmp_path: Path) -> ImportGraphBuilder:
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    return ImportGraphBuilder(builder=builder, workspace=str(tmp_path))


def test_go_import_resolves_to_package_files(tmp_path: Path):
    """A Go import under the module prefix resolves to the target package's .go files."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "internal/api/handler.go",
           'package api\nimport "example.com/proj/internal/db"\nvar _ = db.Get\n')
    _write(tmp_path, "internal/db/store.go", "package db\nfunc Get() {}\n")

    graph = _go_builder(tmp_path).build(staged_files=["internal/api/handler.go"])
    assert graph["internal/api/handler.go"] == {"internal/db/store.go"}


def test_go_stdlib_and_thirdparty_excluded(tmp_path: Path):
    """Imports outside the module prefix (stdlib, third-party) are not graph edges."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "internal/api/handler.go",
           'package api\nimport (\n\t"fmt"\n\t"github.com/other/x"\n)\nvar _ = fmt.Print\n')

    graph = _go_builder(tmp_path).build(staged_files=["internal/api/handler.go"])
    assert graph["internal/api/handler.go"] == set()


def test_go_test_files_excluded_as_targets(tmp_path: Path):
    """Importing a package pulls its .go files but not its _test.go files."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "internal/api/h.go",
           'package api\nimport "example.com/proj/internal/db"\nvar _ = db.Get\n')
    _write(tmp_path, "internal/db/store.go", "package db\nfunc Get() {}\n")
    _write(tmp_path, "internal/db/store_test.go", "package db\n")

    graph = _go_builder(tmp_path).build(staged_files=["internal/api/h.go"])
    assert graph["internal/api/h.go"] == {"internal/db/store.go"}


def test_go_transitive_closure(tmp_path: Path):
    """a imports b, b imports c -> closure expands through Go packages."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "a/a.go", 'package a\nimport "example.com/proj/b"\nvar _ = b.X\n')
    _write(tmp_path, "b/b.go", 'package b\nimport "example.com/proj/c"\nvar X = c.Y\n')
    _write(tmp_path, "c/c.go", "package c\nvar Y = 1\n")

    graph = _go_builder(tmp_path).build(staged_files=["a/a.go"])
    assert graph["a/a.go"] == {"b/b.go"}
    assert graph["b/b.go"] == {"c/c.go"}
    assert graph["c/c.go"] == set()


def test_go_no_gomod_yields_no_edges(tmp_path: Path):
    """Without go.mod the module prefix is unknown, so no local imports resolve."""
    _write(tmp_path, "internal/api/h.go",
           'package api\nimport "example.com/proj/internal/db"\nvar _ = db.Get\n')
    _write(tmp_path, "internal/db/store.go", "package db\nfunc Get() {}\n")

    graph = _go_builder(tmp_path).build(staged_files=["internal/api/h.go"])
    assert graph["internal/api/h.go"] == set()


# --- C# namespace resolution ---

def _cs_available() -> bool:
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    return parse("class C { }", Needs.AST_CSHARP) is not None


def test_csharp_using_resolves_to_namespace_files(tmp_path: Path):
    """A `using X.Y` resolves to every file declaring `namespace X.Y`."""
    if not _cs_available():
        import pytest
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "src/Api/Handler.cs",
           "using App.Db;\nnamespace App.Api;\npublic class Handler { }\n")
    _write(tmp_path, "src/Db/Store.cs", "namespace App.Db;\npublic class Store { }\n")
    _write(tmp_path, "src/Db/Repo.cs", "namespace App.Db;\npublic class Repo { }\n")

    graph = _go_builder(tmp_path).build(staged_files=["src/Api/Handler.cs"])
    assert graph["src/Api/Handler.cs"] == {"src/Db/Store.cs", "src/Db/Repo.cs"}


def test_csharp_external_namespace_excluded(tmp_path: Path):
    """A using of a namespace declared nowhere in the workspace is not an edge."""
    if not _cs_available():
        import pytest
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "src/Api/Handler.cs",
           "using System;\nusing System.Linq;\nnamespace App.Api;\npublic class Handler { }\n")

    graph = _go_builder(tmp_path).build(staged_files=["src/Api/Handler.cs"])
    assert graph["src/Api/Handler.cs"] == set()


def test_csharp_transitive_closure(tmp_path: Path):
    """a uses b's namespace, b uses c's -> closure expands through C# files."""
    if not _cs_available():
        import pytest
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "a/A.cs", "using App.B;\nnamespace App.A;\npublic class A { }\n")
    _write(tmp_path, "b/B.cs", "using App.C;\nnamespace App.B;\npublic class B { }\n")
    _write(tmp_path, "c/C.cs", "namespace App.C;\npublic class C { }\n")

    graph = _go_builder(tmp_path).build(staged_files=["a/A.cs"])
    assert graph["a/A.cs"] == {"b/B.cs"}
    assert graph["b/B.cs"] == {"c/C.cs"}
    assert graph["c/C.cs"] == set()


def test_csharp_self_namespace_not_self_edge(tmp_path: Path):
    """A file that both declares and uses its own namespace produces no self-edge."""
    if not _cs_available():
        import pytest
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "src/App/A.cs", "using App.Core;\nnamespace App.Core;\npublic class A { }\n")
    _write(tmp_path, "src/App/B.cs", "namespace App.Core;\npublic class B { }\n")

    graph = _go_builder(tmp_path).build(staged_files=["src/App/A.cs"])
    assert graph["src/App/A.cs"] == {"src/App/B.cs"}
