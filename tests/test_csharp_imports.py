"""Tests for CSharpNamespaceResolver: `using` -> namespace-declaring files."""
from pathlib import Path
import pytest
from enforcer.context import FileContextBuilder
from enforcer.csharp_imports import CSharpNamespaceResolver
from enforcer.parsers.tree_sitter import parse
from enforcer.types import Needs


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resolver(tmp_path: Path) -> CSharpNamespaceResolver:
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
    return CSharpNamespaceResolver(builder=builder, workspace=str(tmp_path))


def test_using_resolves_to_declaring_files(tmp_path: Path):
    """A `using X.Y` resolves to every file declaring `namespace X.Y`, with using line."""
    _write(tmp_path, "src/Api/Handler.cs",
           "using App.Db;\nnamespace App.Api;\npublic class Handler { }\n")
    _write(tmp_path, "src/Db/Store.cs", "namespace App.Db;\npublic class Store { }\n")
    _write(tmp_path, "src/Db/Repo.cs", "namespace App.Db;\npublic class Repo { }\n")

    _res = _resolver(tmp_path).resolve("src/Api/Handler.cs")
    resolved, lines = _res.targets, _res.lines
    assert resolved == {"src/Db/Store.cs", "src/Db/Repo.cs"}
    assert lines["src/Db/Store.cs"] == 1 and lines["src/Db/Repo.cs"] == 1


def test_external_namespace_excluded(tmp_path: Path):
    """A using of a namespace declared nowhere in the workspace is not an edge."""
    _write(tmp_path, "src/Api/Handler.cs",
           "using System;\nusing System.Linq;\nnamespace App.Api;\npublic class Handler { }\n")

    _res = _resolver(tmp_path).resolve("src/Api/Handler.cs")
    resolved, lines = _res.targets, _res.lines
    assert resolved == set()


def test_self_namespace_not_self_edge(tmp_path: Path):
    """A file that both declares and uses its own namespace produces no self-edge."""
    _write(tmp_path, "src/App/A.cs", "using App.Core;\nnamespace App.Core;\npublic class A { }\n")
    _write(tmp_path, "src/App/B.cs", "namespace App.Core;\npublic class B { }\n")

    resolved = _resolver(tmp_path).resolve("src/App/A.cs").targets
    assert resolved == {"src/App/B.cs"}


def test_nested_namespace_resolves(tmp_path: Path):
    """A using of a nested namespace resolves to the file declaring `Outer.Inner`."""
    _write(tmp_path, "src/Domain/Models.cs",
           "namespace App {\n    namespace Domain {\n        public class M { }\n    }\n}\n")
    _write(tmp_path, "src/Api/Handler.cs",
           "using App.Domain;\nnamespace App.Api;\npublic class Handler { }\n")

    resolved = _resolver(tmp_path).resolve("src/Api/Handler.cs").targets
    assert resolved == {"src/Domain/Models.cs"}
