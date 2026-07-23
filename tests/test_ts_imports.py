"""Tests for TsImportResolver: relative specifiers -> on-disk TS/JS files."""
from pathlib import Path
import pytest
from enforcer.context import FileContextBuilder
from enforcer.ts_imports import TsImportResolver
from enforcer.parsers.tree_sitter import parse
from enforcer.types import ImportResult, Needs


def _write(tmp_path: Path, rel: str, content: str = "export const x = 1;\n") -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resolver(tmp_path: Path) -> TsImportResolver:
    if parse("const x = 1;", Needs.AST_TS) is None:
        pytest.skip("tree-sitter typescript grammar not available")
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    return TsImportResolver(builder, str(tmp_path))


def test_relative_import_resolves_to_file(tmp_path):
    """`import { x } from './b'` resolves to b.ts with the import line."""
    _write(tmp_path, "src/b.ts")
    _write(tmp_path, "src/a.ts", "import { x } from './b';\n")
    result = _resolver(tmp_path).resolve("src/a.ts")
    assert isinstance(result, ImportResult)
    assert "src/b.ts" in result.targets
    assert result.lines["src/b.ts"] == 1


def test_parent_relative_import_resolves(tmp_path):
    """`from '../lib/util'` resolves across directories."""
    _write(tmp_path, "lib/util.ts")
    _write(tmp_path, "src/a.ts", "import { u } from '../lib/util';\n")
    assert "lib/util.ts" in _resolver(tmp_path).resolve("src/a.ts").targets


def test_index_resolution(tmp_path):
    """A directory specifier resolves to its index file."""
    _write(tmp_path, "src/comp/index.ts")
    _write(tmp_path, "src/a.ts", "import { C } from './comp';\n")
    assert "src/comp/index.ts" in _resolver(tmp_path).resolve("src/a.ts").targets


def test_bare_specifier_resolves_to_nothing(tmp_path):
    """A bare/aliased package specifier is not a local edge."""
    _write(tmp_path, "src/a.ts", "import { of } from 'rxjs';\n")
    assert _resolver(tmp_path).resolve("src/a.ts").targets == set()


def test_missing_file_yields_empty(tmp_path):
    """An absent file resolves to an empty ImportResult."""
    assert _resolver(tmp_path).resolve("nope.ts").targets == set()
