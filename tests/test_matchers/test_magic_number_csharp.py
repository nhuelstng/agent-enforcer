"""C#-language tests for MagicNumberMatcher."""
import pytest
from enforcer.matchers.magic_number import MagicNumberMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="C.cs", raw=source, ast=tree)


def _wrap(body: str) -> str:
    return f"public class C {{\n    public int M() {{\n        {body}\n    }}\n}}\n"


@pytest.mark.parametrize("body", [
    "return x * 42;",
    "var t = 100; return t;",
    "return Compute(3600);",
])
def test_csharp_magic_flags(body):
    """A magic literal inside a method body is flagged."""
    matcher = MagicNumberMatcher(needs=Needs.AST_CSHARP)
    assert matcher.find(_cs_ctx(_wrap(body)))


@pytest.mark.parametrize("body", [
    "return x + 1;",
    "return -5;",
    "const int Max = 100; return Max;",
])
def test_csharp_magic_clean(body):
    """Small ints and named local constants are not flagged."""
    matcher = MagicNumberMatcher(needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(_wrap(body)))


@pytest.mark.parametrize("source", [
    "public enum Http { Ok = 200, NotFound = 404 }\n",
    "[Range(1, 100)]\npublic class C { }\n",
    "public class C { public const int Max = 100; }\n",
    "public class C { public void M(int timeout = 30) { } }\n",
])
def test_csharp_non_body_positions_clean(source):
    """Enum members, attribute args, const fields and parameter defaults are excluded."""
    matcher = MagicNumberMatcher(needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(source))
