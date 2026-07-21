"""C#-language tests for ArchitectureMatcher (namespace import-graph driven rules)."""
from pathlib import Path
import pytest
from enforcer.import_graph import ImportGraphBuilder
from enforcer.context import FileContextBuilder
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.types import FileContext, Needs
from enforcer.parsers.tree_sitter import parse


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _setup(tmp_path: Path) -> None:
    """Lay down a few sibling slices under src/, each its own namespace."""
    for slice_ in ("Db", "Cache", "Auth"):
        _write(tmp_path, f"src/{slice_}/{slice_}.cs",
                f"namespace App.{slice_};\npublic class {slice_} {{ }}\n")
    _write(tmp_path, "src/Api/Sub/Sub.cs",
           "namespace App.Api.Sub;\npublic class Sub { }\n")


def _run(tmp_path: Path, importer_src: str, matcher: ArchitectureMatcher):
    """Write the importer, build the graph, run the matcher on it."""
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "src/Api/Handler.cs", importer_src)
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph_builder = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = graph_builder.build(staged_files=["src/Api/Handler.cs"])
    ctx = FileContext(path="src/Api/Handler.cs", raw=importer_src,
                      ast=parse(importer_src, Needs.AST_CSHARP))
    return matcher.find(ctx, {"__import_graph__": graph,
                              "__import_lines__": graph_builder.import_lines})


@pytest.mark.parametrize("sibling", ["Db", "Cache", "Auth"])
def test_csharp_sibling_import_flags(tmp_path: Path, sibling: str):
    """Importing a peer slice under an isolate_siblings root is a violation."""
    _setup(tmp_path)
    src = f"using App.{sibling};\n\nnamespace App.Api;\npublic class Handler {{ }}\n"
    matcher = ArchitectureMatcher(isolate_siblings=["src"], needs=Needs.AST_CSHARP)
    matches = _run(tmp_path, src, matcher)
    assert matches
    assert f"Api -> {sibling}" in matches[0].matched_value


@pytest.mark.parametrize("importer_src", [
    "using System;\n\nnamespace App.Api;\npublic class Handler { }\n",
    "namespace App.Api;\npublic class Handler { }\n",
    "using App.Api.Sub;\n\nnamespace App.Api;\npublic class Handler { }\n",
])
def test_csharp_no_sibling_violation_clean(tmp_path: Path, importer_src: str):
    """External usings, no usings, and same-slice usings raise no sibling violation."""
    _setup(tmp_path)
    matcher = ArchitectureMatcher(isolate_siblings=["src"], needs=Needs.AST_CSHARP)
    assert not _run(tmp_path, importer_src, matcher)


def test_csharp_sibling_violation_line_attribution(tmp_path: Path):
    """The violation is reported on the offending using's line."""
    _setup(tmp_path)
    src = "using System;\nusing App.Db;\n\nnamespace App.Api;\npublic class Handler { }\n"
    matcher = ArchitectureMatcher(isolate_siblings=["src"], needs=Needs.AST_CSHARP)
    matches = _run(tmp_path, src, matcher)
    assert len(matches) == 1
    assert matches[0].line == 2  # the `using App.Db;` line


def test_csharp_layer_dag_violation(tmp_path: Path):
    """A forbidden layer edge (api -> db) is flagged via layer globs."""
    _setup(tmp_path)
    src = "using App.Db;\n\nnamespace App.Api;\npublic class Handler { }\n"
    matcher = ArchitectureMatcher(
        layers={"api": ["src/Api/**"], "db": ["src/Db/**"]},
        allowed_edges=[],
        forbid_implicit=True,
        needs=Needs.AST_CSHARP,
    )
    matches = _run(tmp_path, src, matcher)
    assert len(matches) == 1
    assert matches[0].matched_value == "api -> db"


def test_csharp_layer_dag_allowed_edge_clean(tmp_path: Path):
    """An explicitly allowed layer edge is not flagged."""
    _setup(tmp_path)
    src = "using App.Db;\n\nnamespace App.Api;\npublic class Handler { }\n"
    matcher = ArchitectureMatcher(
        layers={"api": ["src/Api/**"], "db": ["src/Db/**"]},
        allowed_edges=[("api", "db")],
        forbid_implicit=True,
        needs=Needs.AST_CSHARP,
    )
    assert not _run(tmp_path, src, matcher)


def test_csharp_nested_namespace_resolves(tmp_path: Path):
    """A using of a nested namespace resolves to the file declaring `Outer.Inner`."""
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    _write(tmp_path, "src/Domain/Models.cs",
           "namespace App {\n    namespace Domain {\n        public class M { }\n    }\n}\n")
    _write(tmp_path, "src/Api/Handler.cs",
           "using App.Domain;\n\nnamespace App.Api;\npublic class Handler { }\n")
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    graph = ImportGraphBuilder(builder=builder, workspace=str(tmp_path)).build(
        staged_files=["src/Api/Handler.cs"])
    assert "src/Domain/Models.cs" in graph["src/Api/Handler.cs"]
