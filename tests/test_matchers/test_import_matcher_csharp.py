"""C#-language tests for ImportMatcher (forbidden using directives)."""
import pytest
from enforcer.matchers.import_matcher import ImportMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="Widget.cs", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "using Banned.Thing;\n\npublic class C { }\n",
    "using System;\nusing Legacy.Api;\n\npublic class C { }\n",
    "using Internal.Detail;\n\npublic class C { }\n",
])
def test_csharp_forbidden_using_flags(src):
    """Should flag using directives matching a forbidden pattern."""
    matcher = ImportMatcher(
        forbidden_patterns=[r"Banned", r"Legacy", r"Internal"], needs=Needs.AST_CSHARP,
    )
    assert matcher.find(_cs_ctx(src))


@pytest.mark.parametrize("src", [
    "using System;\n\npublic class C { }\n",
    "using System.Collections.Generic;\n\npublic class C { }\n",
    "using System.Linq;\n\npublic class C { }\n",
])
def test_csharp_allowed_using_clean(src):
    """Should not flag using directives that match no forbidden pattern."""
    matcher = ImportMatcher(
        forbidden_patterns=[r"Banned", r"Legacy", r"Internal"], needs=Needs.AST_CSHARP,
    )
    assert not matcher.find(_cs_ctx(src))


def test_csharp_reports_using_text():
    """The reported value is the offending using directive's full text."""
    src = "using System;\nusing Banned.Thing;\n\npublic class C { }\n"
    matches = ImportMatcher(forbidden_patterns=[r"Banned"], needs=Needs.AST_CSHARP).find(_cs_ctx(src))
    assert [m.matched_value for m in matches] == ["using Banned.Thing;"]
