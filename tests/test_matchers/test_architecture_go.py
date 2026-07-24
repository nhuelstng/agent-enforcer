"""Go-language tests for ArchitectureMatcher (import-graph driven layer/sibling rules)."""
from pathlib import Path
import pytest
from enforcer.import_graph import ImportGraphBuilder
from enforcer.context import FileContextBuilder
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.types import FileContext, Needs
from enforcer.parsers.tree_sitter import parse

_GOMOD = "module example.com/proj\n\ngo 1.22\n"


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _setup(tmp_path: Path) -> None:
    """Lay down a go.mod and a few sibling packages under internal/."""
    _write(tmp_path, "go.mod", _GOMOD)
    for pkg in ("db", "cache", "auth"):
        _write(tmp_path, f"internal/{pkg}/{pkg}.go", f"package {pkg}\nfunc X() {{}}\n")
    _write(tmp_path, "internal/api/sub/sub.go", "package sub\nfunc X() {}\n")


def _run(tmp_path: Path, importer_src: str, matcher: ArchitectureMatcher):
    """Write the importer, build the graph, run the matcher on it."""
    _write(tmp_path, "internal/api/handler.go", importer_src)
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=["internal/api/handler.go"])
    ctx = FileContext(path="internal/api/handler.go", raw=importer_src)
    ctx.ast = parse(importer_src, Needs.AST_GO)
    return matcher.find(ctx, {"__import_graph__": graph, "__import_lines__": gb.import_lines})


@pytest.mark.parametrize("sibling", ["db", "cache", "auth"])
def test_go_sibling_import_flags(tmp_path: Path, sibling: str):
    """Importing a peer slice under an isolate_siblings root is a violation."""
    _setup(tmp_path)
    src = f'package api\nimport "example.com/proj/internal/{sibling}"\nvar _ = {sibling}.X\n'
    matcher = ArchitectureMatcher(isolate_siblings=["internal"], needs=Needs.AST_GO)
    matches = _run(tmp_path, src, matcher)
    assert matches
    assert f"api -> {sibling}" in matches[0].matched_value


@pytest.mark.parametrize("importer_src", [
    'package api\nimport "fmt"\nvar _ = fmt.Print\n',
    'package api\nfunc F() {}\n',
    'package api\nimport "example.com/proj/internal/api/sub"\nvar _ = sub.X\n',
])
def test_go_no_sibling_violation_clean(tmp_path: Path, importer_src: str):
    """Stdlib imports, no imports, and same-slice imports raise no sibling violation."""
    _setup(tmp_path)
    matcher = ArchitectureMatcher(isolate_siblings=["internal"], needs=Needs.AST_GO)
    assert not _run(tmp_path, importer_src, matcher)


def test_go_sibling_violation_line_attribution(tmp_path: Path):
    """The violation is reported on the offending import's line."""
    _setup(tmp_path)
    src = 'package api\n\nimport (\n\t"fmt"\n\t"example.com/proj/internal/db"\n)\n\nvar _ = fmt.Print\nvar _ = db.X\n'
    matcher = ArchitectureMatcher(isolate_siblings=["internal"], needs=Needs.AST_GO)
    matches = _run(tmp_path, src, matcher)
    assert len(matches) == 1
    assert matches[0].line == 5  # the internal/db import line


def test_go_layer_dag_violation(tmp_path: Path):
    """A forbidden layer edge (api -> db) is flagged via layer globs."""
    _setup(tmp_path)
    src = 'package api\nimport "example.com/proj/internal/db"\nvar _ = db.X\n'
    matcher = ArchitectureMatcher(
        layers={"api": ["internal/api/**"], "db": ["internal/db/**"]},
        allowed_edges=[],
        forbid_implicit=True,
        needs=Needs.AST_GO,
    )
    matches = _run(tmp_path, src, matcher)
    assert len(matches) == 1
    assert matches[0].matched_value == "api -> db"


def test_go_layer_dag_allowed_edge_clean(tmp_path: Path):
    """An explicitly allowed layer edge is not flagged."""
    _setup(tmp_path)
    src = 'package api\nimport "example.com/proj/internal/db"\nvar _ = db.X\n'
    matcher = ArchitectureMatcher(
        layers={"api": ["internal/api/**"], "db": ["internal/db/**"]},
        allowed_edges=[("api", "db")],
        forbid_implicit=True,
        needs=Needs.AST_GO,
    )
    assert not _run(tmp_path, src, matcher)
