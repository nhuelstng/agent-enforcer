"""Tests for InvocationMatcher (banning specific method/function calls)."""
import pytest
from enforcer.matchers.invocation import InvocationMatcher
from enforcer.types import FileContext, Needs


def _ctx(source: str, lang: Needs, path: str = "C.cs") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, lang)
    if tree is None:
        pytest.skip("tree-sitter grammar not available")
    return FileContext(path=path, raw=source, ast=tree)


def _cs(body: str) -> str:
    return f"public class C {{\n    public void M() {{\n        {body}\n    }}\n}}\n"


@pytest.mark.parametrize("body,pattern", [
    ("task.Wait();", r"\.Wait$"),
    ("var a = db.Users.ToList();", r"\.ToList$"),
    ("provider.GetService();", r"GetService"),
])
def test_invocation_csharp_flags(body, pattern):
    """A banned C# call is flagged."""
    matcher = InvocationMatcher(pattern=pattern, needs=Needs.AST_CSHARP)
    assert matcher.find(_ctx(_cs(body), Needs.AST_CSHARP))


@pytest.mark.parametrize("body,pattern", [
    ("var a = db.Users.ToListAsync();", r"\.ToList$"),   # Async variant, not .ToList
    ("await task;", r"\.Wait$"),
    ("Log(x);", r"GetService"),
])
def test_invocation_csharp_clean(body, pattern):
    """A call that doesn't match the pattern is not flagged."""
    matcher = InvocationMatcher(pattern=pattern, needs=Needs.AST_CSHARP)
    assert not matcher.find(_ctx(_cs(body), Needs.AST_CSHARP))


@pytest.mark.parametrize("source,pattern", [
    ("x = obj.foo()\n", r"\.foo$"),
    ("result = requests.get(url)\n", r"requests\.get"),
    ("y = eval(code)\n", r"^eval$"),
])
def test_invocation_python_flags(source, pattern):
    """The matcher is language-generic — Python calls work too."""
    matcher = InvocationMatcher(pattern=pattern, needs=Needs.AST_PY)
    assert matcher.find(_ctx(source, Needs.AST_PY, path="c.py"))
