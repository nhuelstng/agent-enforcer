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
