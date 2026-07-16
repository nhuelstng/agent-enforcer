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
