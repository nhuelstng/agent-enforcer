"""C#-language tests for CycleMatcher (import cycles via the namespace graph)."""
from pathlib import Path
import pytest
from enforcer.import_graph import ImportGraphBuilder
from enforcer.context import FileContextBuilder
from enforcer.matchers.import_cycle import CycleMatcher
from enforcer.types import FileContext, Needs
from enforcer.parsers.tree_sitter import parse


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _graph(tmp_path: Path, staged: list[str]):
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    gb = ImportGraphBuilder(builder=builder, workspace=str(tmp_path))
    graph = gb.build(staged_files=staged)
    return graph, gb


def _cycle_triple(tmp_path: Path) -> None:
    """A -> B -> C -> A: every file's using lies on the cycle."""
    _write(tmp_path, "src/A/A.cs", "using App.B;\n\nnamespace App.A;\npublic class A { }\n")
    _write(tmp_path, "src/B/B.cs", "using App.C;\n\nnamespace App.B;\npublic class B { }\n")
    _write(tmp_path, "src/C/C.cs", "using App.A;\n\nnamespace App.C;\npublic class C { }\n")


@pytest.mark.parametrize("path", ["src/A/A.cs", "src/B/B.cs", "src/C/C.cs"])
def test_csharp_cycle_flags(tmp_path: Path, path: str):
    """Each file on a three-node import cycle has its using flagged."""
    _cycle_triple(tmp_path)
    graph, gb = _graph(tmp_path, ["src/A/A.cs", "src/B/B.cs", "src/C/C.cs"])
    ctx = FileContext(path=path, raw=(tmp_path / path).read_text(),
                      ast=parse((tmp_path / path).read_text(), Needs.AST_CSHARP))
    matches = CycleMatcher(needs=Needs.AST_CSHARP).find(
        ctx, {"__import_graph__": graph, "__import_lines__": gb.import_lines})
    assert matches
    assert matches[0].line == 1  # the offending `using` line


@pytest.mark.parametrize("importer", [
    "using System;\n\nnamespace App.A;\npublic class A { }\n",
    "using App.B;\n\nnamespace App.A;\npublic class A { }\n",   # B does not use A back
    "namespace App.A;\npublic class A { }\n",
])
def test_csharp_no_cycle_clean(tmp_path: Path, importer: str):
    """Acyclic, external, or one-directional usings raise no cycle."""
    _write(tmp_path, "src/B/B.cs", "namespace App.B;\npublic class B { }\n")
    _write(tmp_path, "src/A/A.cs", importer)
    graph, gb = _graph(tmp_path, ["src/A/A.cs", "src/B/B.cs"])
    ctx = FileContext(path="src/A/A.cs", raw=importer,
                      ast=parse(importer, Needs.AST_CSHARP))
    matches = CycleMatcher(needs=Needs.AST_CSHARP).find(
        ctx, {"__import_graph__": graph, "__import_lines__": gb.import_lines})
    assert not matches
