"""C#-language tests for AstNodeMatcher (scoped/typed node detection)."""
import pytest
from enforcer.matchers.ast_node import AstNodeMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="Widget.cs", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "public class C {\n    void M() { if (a) { } }\n}\n",
    "public class C {\n    void M() { if (a) { } if (b) { } }\n}\n",
    "public class C {\n    void M() { if (a) { if (b) { } } }\n}\n",
])
def test_csharp_if_statement_flags(src):
    """Should find C# if_statement nodes by type."""
    matcher = AstNodeMatcher(node_type="if_statement", needs=Needs.AST_CSHARP)
    assert matcher.find(_cs_ctx(src))


@pytest.mark.parametrize("src", [
    "public class C { }\n",
    "public interface I { void N(); }\n",
    "public enum Color { Red, Green }\n",
])
def test_csharp_if_statement_clean(src):
    """Should not report if_statement in files that have none."""
    matcher = AstNodeMatcher(node_type="if_statement", needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(src))


def test_csharp_finds_using_directives():
    """Each using directive is a using_directive node."""
    src = "using System;\nusing System.Linq;\n\npublic class C { }\n"
    matcher = AstNodeMatcher(node_type="using_directive", needs=Needs.AST_CSHARP)
    assert len(matcher.find(_cs_ctx(src))) == 2


def test_csharp_scope_limits_to_class_body():
    """A class scope restricts matching to type-declaration bodies."""
    src = (
        "public class C {\n    void M() { }\n}\n"
        "public interface I {\n    void N();\n}\n"
    )
    matcher = AstNodeMatcher(node_type="method_declaration", scope="class", needs=Needs.AST_CSHARP)
    assert len(matcher.find(_cs_ctx(src))) >= 1
