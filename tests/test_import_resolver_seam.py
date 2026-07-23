"""The ImportResolver seam: every language adapter satisfies one Protocol + result shape."""
from enforcer.context import FileContextBuilder
from enforcer.types import ImportResolver, ImportResult
from enforcer.python_imports import PythonImportResolver
from enforcer.ts_imports import TsImportResolver
from enforcer.go_imports import GoImportResolver
from enforcer.csharp_imports import CSharpNamespaceResolver


def _builder(tmp_path) -> FileContextBuilder:
    return FileContextBuilder(rules=[], workspace=str(tmp_path))


def test_all_adapters_are_import_resolvers(tmp_path):
    """Each language adapter structurally satisfies the ImportResolver Protocol."""
    b = _builder(tmp_path)
    adapters = [
        PythonImportResolver(b, str(tmp_path)),
        TsImportResolver(b, str(tmp_path)),
        GoImportResolver(b, str(tmp_path)),
        CSharpNamespaceResolver(b, str(tmp_path)),
    ]
    for a in adapters:
        assert isinstance(a, ImportResolver)


def test_python_resolver_returns_import_result(tmp_path):
    """resolve() returns an ImportResult with targets + line attribution."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text("import pkg.b\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")

    result = PythonImportResolver(_builder(tmp_path), str(tmp_path)).resolve("pkg/a.py")
    assert isinstance(result, ImportResult)
    assert "pkg/b.py" in result.targets
    assert result.lines["pkg/b.py"] == 1


def test_missing_file_yields_empty_result(tmp_path):
    """An unparseable/absent file resolves to an empty ImportResult, not an error."""
    result = PythonImportResolver(_builder(tmp_path), str(tmp_path)).resolve("nope.py")
    assert result.targets == set()
