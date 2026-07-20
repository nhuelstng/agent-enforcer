"""C#-language tests for NamingConventionMatcher (declaration-name patterns)."""
import pytest
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="Widget.cs", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "public class widget { }\n",
    "public class my_type { }\n",
    "public class lowercase { }\n",
])
def test_csharp_class_pascalcase_flags(src):
    """Should flag C# classes whose names are not PascalCase."""
    matcher = NamingConventionMatcher(
        declaration_types=["class_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_CSHARP,
    )
    assert matcher.find(_cs_ctx(src))


@pytest.mark.parametrize("src", [
    "public class Widget { }\n",
    "public class OrderService { }\n",
    "public class HttpClient { }\n",
])
def test_csharp_class_pascalcase_clean(src):
    """Should not flag PascalCase C# class names."""
    matcher = NamingConventionMatcher(
        declaration_types=["class_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_CSHARP,
    )
    assert not matcher.find(_cs_ctx(src))


def test_csharp_interface_i_prefix():
    """Interfaces must start with 'I'; a non-conforming name is flagged."""
    ctx = _cs_ctx("public interface Widget { }\n")
    matches = NamingConventionMatcher(
        declaration_types=["interface_declaration"], pattern=r"^I[A-Z]", needs=Needs.AST_CSHARP,
    ).find(ctx)
    assert [m.matched_value for m in matches] == ["Widget"]


def test_csharp_method_name_not_return_type():
    """Method name extraction skips the return type; a bad method name is flagged."""
    src = "public class C {\n    public Widget make() { return null; }\n}\n"
    matches = NamingConventionMatcher(
        declaration_types=["method_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_CSHARP,
    ).find(_cs_ctx(src))
    assert [m.matched_value for m in matches] == ["make"]
