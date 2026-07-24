"""Tests for CycleMatcher: flags import edges that lie on a dependency cycle."""
import pytest
from enforcer.matchers import CycleMatcher  # also asserts registration
from enforcer.types import FileContext


def _ctx(path: str) -> FileContext:
    return FileContext(path=path, raw="# stub")


@pytest.mark.parametrize("graph,path,expected", [
    ({"a.py": {"b.py"}, "b.py": {"a.py"}}, "a.py", "a.py -> b.py -> a.py"),
    ({"a.py": {"b.py"}, "b.py": {"a.py"}}, "b.py", "b.py -> a.py -> b.py"),
    ({"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": {"a.py"}}, "a.py", "a.py -> b.py -> c.py -> a.py"),
    # same-directory cycle: no layer edge crossed -- the differentiator vs ArchitectureMatcher.
    ({"pkg/x.py": {"pkg/y.py"}, "pkg/y.py": {"pkg/x.py"}}, "pkg/x.py", "pkg/x.py -> pkg/y.py -> pkg/x.py"),
])
def test_cycle_detected_fail(graph, path, expected):
    """Positive: an edge that closes a cycle is flagged, with the cycle rendered."""
    matches = CycleMatcher().find(_ctx(path), {"__import_graph__": graph})
    assert matches
    assert matches[0].matched_value == expected


@pytest.mark.parametrize("graph,path", [
    ({"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": set()}, "a.py"),          # DAG
    ({"a.py": {"a.py"}}, "a.py"),                                            # self-import ignored
    ({"a.py": {"b.py", "c.py"}, "b.py": {"d.py"}, "c.py": {"d.py"}, "d.py": set()}, "a.py"),  # diamond
    ({}, "missing.py"),                                                      # node absent
])
def test_no_cycle_success(graph, path):
    """Negative: acyclic edges, self-imports, and absent nodes are not flagged."""
    assert CycleMatcher().find(_ctx(path), {"__import_graph__": graph}) == []


def test_line_attribution():
    """The finding is attributed to the line of the offending import."""
    ctx = {"__import_graph__": {"a.py": {"b.py"}, "b.py": {"a.py"}},
           "__import_lines__": {"a.py": {"b.py": 7}}}
    assert CycleMatcher().find(_ctx("a.py"), ctx)[0].line == 7


def test_go_cycle_line_attribution_regression(tmp_path):
    """Regression: a Go edge on a cycle reports its real import line, not 0.

    Before uniform ImportResult.lines, the Go resolver recorded no lines and
    CycleMatcher (which has no AST fallback) attributed every Go cycle edge to line 0."""
    from enforcer.import_graph import ImportGraphBuilder
    from enforcer.context import FileContextBuilder
    (tmp_path / "go.mod").write_text("module example.com/proj\n\ngo 1.22\n")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "a.go").write_text('package a\n\nimport "example.com/proj/b"\n\nvar _ = b.X\n')
    (tmp_path / "b" / "b.go").write_text('package b\n\nimport "example.com/proj/a"\n\nvar _ = a.Y\n')
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=["a/a.go", "b/b.go"])
    if "b/b.go" not in graph.get("a/a.go", set()):
        pytest.skip("tree-sitter Go grammar not available")
    ctx = {"__import_graph__": graph, "__import_lines__": gb.import_lines}
    matches = CycleMatcher().find(_ctx("a/a.go"), ctx)
    assert len(matches) == 1
    assert matches[0].line == 3  # the `import "example.com/proj/b"` line, not 0


def test_reachability_memoized_across_files():
    """Memoized reachability stays correct when reused across files in one shared_ctx."""
    graph = {"a.py": {"b.py"}, "b.py": {"a.py"}, "c.py": {"a.py"}}
    ctx = {"__import_graph__": graph}
    m = CycleMatcher()
    assert len(m.find(_ctx("a.py"), ctx)) == 1
    assert len(m.find(_ctx("b.py"), ctx)) == 1
    assert m.find(_ctx("c.py"), ctx) == []  # c -> a -> b, never returns to c
    assert "__cycle_reach__" in ctx
