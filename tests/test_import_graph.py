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
