"""Tests for GoImportResolver: go.mod-relative package resolution to .go files."""
from pathlib import Path
import pytest
from enforcer.context import FileContextBuilder
from enforcer.go_imports import GoImportResolver
from enforcer.parsers.tree_sitter import parse
from enforcer.types import Needs

_GOMOD = "module example.com/proj\n\ngo 1.22\n"


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resolver(tmp_path: Path) -> GoImportResolver:
    if parse("package main\n", Needs.AST_GO) is None:
        pytest.skip("tree-sitter go grammar not available")
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    return GoImportResolver(builder=builder, workspace=str(tmp_path))


def test_import_resolves_to_package_files(tmp_path: Path):
    """A local import resolves to every non-test .go file in the target package dir."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "internal/api/h.go",
           'package api\nimport "example.com/proj/internal/db"\nvar _ = db.Get\n')
    _write(tmp_path, "internal/db/store.go", "package db\nfunc Get() {}\n")
    _write(tmp_path, "internal/db/store_test.go", "package db\n")

    assert _resolver(tmp_path).resolve("internal/api/h.go").targets == {"internal/db/store.go"}


def test_stdlib_and_thirdparty_excluded(tmp_path: Path):
    """Imports outside the module prefix (stdlib, third-party) resolve to nothing."""
    _write(tmp_path, "go.mod", _GOMOD)
    _write(tmp_path, "internal/api/h.go",
           'package api\nimport (\n\t"fmt"\n\t"github.com/other/x"\n)\nvar _ = fmt.Print\n')

    assert _resolver(tmp_path).resolve("internal/api/h.go").targets == set()


def test_no_gomod_yields_no_edges(tmp_path: Path):
    """Without go.mod the module prefix is unknown, so no local imports resolve."""
    _write(tmp_path, "internal/api/h.go",
           'package api\nimport "example.com/proj/internal/db"\nvar _ = db.Get\n')
    _write(tmp_path, "internal/db/store.go", "package db\nfunc Get() {}\n")

    assert _resolver(tmp_path).resolve("internal/api/h.go").targets == set()
