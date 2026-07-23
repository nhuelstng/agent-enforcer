"""Tests for PythonImportResolver: dotted imports -> on-disk module paths."""
from pathlib import Path
from enforcer.context import FileContextBuilder
from enforcer.python_imports import PythonImportResolver
from enforcer.types import ImportResult


def _write(tmp_path: Path, rel: str, content: str = "x = 1\n") -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resolver(tmp_path: Path, source_roots=None) -> PythonImportResolver:
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    return PythonImportResolver(builder, str(tmp_path), source_roots)


def test_plain_import_resolves_to_module_file(tmp_path):
    """`import pkg.b` resolves to pkg/b.py with the import's line."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import pkg.b\n")
    _write(tmp_path, "pkg/b.py")
    result = _resolver(tmp_path).resolve("pkg/a.py")
    assert isinstance(result, ImportResult)
    assert "pkg/b.py" in result.targets
    assert result.lines["pkg/b.py"] == 1


def test_from_import_symbol_falls_back_to_parent(tmp_path):
    """`from pkg.b import Thing` (symbol, not submodule) resolves to pkg/b.py."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/b.py", "class Thing: pass\n")
    _write(tmp_path, "pkg/a.py", "from pkg.b import Thing\n")
    assert "pkg/b.py" in _resolver(tmp_path).resolve("pkg/a.py").targets


def test_stdlib_import_resolves_to_nothing(tmp_path):
    """A third-party/stdlib module with no on-disk target is not an edge."""
    _write(tmp_path, "a.py", "import os\nimport sys\n")
    assert _resolver(tmp_path).resolve("a.py").targets == set()


def test_relative_import_deferred(tmp_path):
    """Relative imports are deferred and resolve to nothing."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from . import b\n")
    _write(tmp_path, "pkg/b.py")
    assert _resolver(tmp_path).resolve("pkg/a.py").targets == set()


def test_source_root_prefix_maps_to_subdir(tmp_path):
    """A source_roots prefix rewrites the import to its on-disk directory."""
    _write(tmp_path, "server/app/__init__.py", "")
    _write(tmp_path, "server/app/x.py")
    _write(tmp_path, "server/app/main.py", "import app.x\n")
    r = _resolver(tmp_path, source_roots={"app": "server/app"})
    # 'app.x' -> server/app/... via source root; main.py itself lives under server/app
    assert "server/app/x.py" in r.resolve("server/app/main.py").targets


def test_missing_file_yields_empty(tmp_path):
    """An absent file resolves to an empty ImportResult."""
    assert _resolver(tmp_path).resolve("nope.py").targets == set()
