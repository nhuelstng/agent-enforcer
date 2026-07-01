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
