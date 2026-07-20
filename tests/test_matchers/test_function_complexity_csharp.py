"""C#-language tests for FunctionComplexityMatcher (lines/params/nesting/cyclomatic)."""
import pytest
from enforcer.matchers.function_complexity import FunctionComplexityMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="Widget.cs", raw=source, ast=tree)


def _wrap(members: str) -> str:
    return f"public class C\n{{\n{members}\n}}\n"


@pytest.mark.parametrize("member", [
    "    public int F(int a, int b, int c) { return 0; }",
    "    public int G(int a, int b, int c, int d) { return 0; }",
    "    public void H(string a, string b, string c) { }",
])
def test_csharp_params_flags(member):
    """Should flag C# methods whose parameter count exceeds the budget."""
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_CSHARP)
    assert matcher.find(_cs_ctx(_wrap(member)))


@pytest.mark.parametrize("member", [
    "    public int F(int a) { return 0; }",
    "    public void G() { }",
    "    public int H(int a, int b) { return 0; }",
])
def test_csharp_params_clean(member):
    """Should not flag C# methods within the parameter budget."""
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(_wrap(member)))


_CS_COMPLEX = _wrap(
    "    public int F(int a, int b, int c)\n    {\n"
    "        if (a > 0 && b > 0) { }\n"
    "        switch (c) { case 1: break; case 2: break; default: break; }\n"
    "        foreach (var x in items) { }\n"
    "        return 0;\n    }"
)


def test_csharp_cyclomatic_counts_branches():
    """Cyclomatic = 1 + if + && + 2 non-default cases + foreach = 6."""
    matcher = FunctionComplexityMatcher(metric="cyclomatic", max_value=3, needs=Needs.AST_CSHARP)
    matches = matcher.find(_cs_ctx(_CS_COMPLEX))
    assert len(matches) == 1
    assert int(matches[0].matched_value) == 6


def test_csharp_nesting_counts_foreach_level():
    """Nesting class-method>if>foreach>if reaches depth >= 3."""
    body = _wrap(
        "    public void F()\n    {\n"
        "        if (a) { foreach (var x in xs) { if (b) { } } }\n"
        "    }"
    )
    matcher = FunctionComplexityMatcher(metric="nesting", max_value=2, needs=Needs.AST_CSHARP)
    matches = matcher.find(_cs_ctx(body))
    assert matches and int(matches[0].matched_value) >= 3
