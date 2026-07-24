"""Tests for FunctionComplexityMatcher: function-level complexity metrics."""
from enforcer.matchers.function_complexity import FunctionComplexityMatcher
from enforcer.types import FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def test_function_too_many_lines():
    """Should flag a function exceeding max_lines."""
    source = "def long_func():\n" + "    x = 1\n" * 20 + "\n"
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="lines", max_value=10)
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert int(matches[0].matched_value) > 10

def test_function_ok_lines():
    """Should not flag a function within max_lines."""
    source = "def short_func():\n    x = 1\n"
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="lines", max_value=10)
    assert matcher.find(ctx) == []

def test_function_too_many_params():
    """Should flag a function with too many parameters."""
    source = "def f(a, b, c, d, e, f, g):\n    pass\n"
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="params", max_value=5)
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert int(matches[0].matched_value) == 7

def test_function_ok_params():
    """Should not flag a function with acceptable param count."""
    source = "def f(a, b):\n    pass\n"
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="params", max_value=5)
    assert matcher.find(ctx) == []

def test_function_nesting_depth():
    """Should flag deeply nested functions."""
    source = (
        "def f():\n"
        "    if True:\n"
        "        if True:\n"
        "            if True:\n"
        "                if True:\n"
        "                    x = 1\n"
    )
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="nesting", max_value=3)
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert int(matches[0].matched_value) >= 4

def test_multiple_functions_flagged():
    """Should flag multiple functions in the same file."""
    source = (
        "def long_one():\n" + "    x = 1\n" * 20 + "\n"
        "def short_one():\n    x = 1\n"
        "def also_long():\n" + "    y = 2\n" * 20 + "\n"
    )
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="lines", max_value=10)
    matches = matcher.find(ctx)
    assert len(matches) == 2

def test_cyclomatic_complexity():
    """Should count decision points (if/for/while/and/or/elif)."""
    source = (
        "def f():\n"
        "    if True:\n"
        "        pass\n"
        "    if True:\n"
        "        pass\n"
        "    if True:\n"
        "        pass\n"
        "    if True:\n"
        "        pass\n"
    )
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="cyclomatic", max_value=3)
    matches = matcher.find(ctx)
    assert len(matches) == 1
    # 4 ifs = cyclomatic complexity 5 (1 base + 4 decision points)
    assert int(matches[0].matched_value) == 5

def test_typescript_methods():
    """Should work with TypeScript class methods."""
    source = (
        "class Foo {\n"
        "  bigMethod() {\n"
        + "    this.x = 1;\n" * 20
        + "  }\n"
        "}\n"
    )
    ctx = _make_ctx(source, lang=Needs.AST_TS)
    matcher = FunctionComplexityMatcher(metric="lines", max_value=10)
    matches = matcher.find(ctx)
    assert len(matches) == 1

def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="def f(): pass")
    matcher = FunctionComplexityMatcher(metric="lines", max_value=1)
    assert matcher.find(ctx) == []

def test_splat_params_counted():
    """Should count *args and **kwargs as parameters."""
    source = "def f(a, b, *args, **kwargs):\n    pass\n"
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="params", max_value=3)
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert int(matches[0].matched_value) == 4

def test_nested_function_cyclomatic_isolated():
    """Cyclomatic of outer function should not include inner function's decisions."""
    source = (
        "def outer():\n"
        "    if True:\n"
        "        pass\n"
        "    def inner():\n"
        "        if True:\n"
        "            pass\n"
        "        if True:\n"
        "            pass\n"
    )
    ctx = _make_ctx(source)
    matcher = FunctionComplexityMatcher(metric="cyclomatic", max_value=2)
    matches = matcher.find(ctx)
    # outer: 1 + 1 if = 2 (not > 2, no match)
    # inner: 1 + 2 ifs = 3 (> 2, match)
    assert len(matches) == 1


import pytest


@pytest.mark.parametrize("raw", [
    "def f():\n" + "    x = 1\n" * 8,
    "def g():\n" + "    y = 2\n" * 12,
    "def h():\n" + "    z = 3\n" * 20,
])
def test_complexity_flags_violation(raw):
    """Functions exceeding max_lines are flagged."""
    assert FunctionComplexityMatcher(metric="lines", max_value=3).find(_make_ctx(raw))


@pytest.mark.parametrize("raw", [
    "def f():\n    x = 1\n",
    "def g():\n    y = 2\n",
    "def h():\n    return 3\n",
])
def test_complexity_passes_clean(raw):
    """Short functions within max_lines pass cleanly."""
    assert not FunctionComplexityMatcher(metric="lines", max_value=3).find(_make_ctx(raw))
