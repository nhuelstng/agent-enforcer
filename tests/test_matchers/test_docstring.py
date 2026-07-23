"""Tests for DocstringMatcher: flags public functions missing docstrings."""
from enforcer.matchers.docstring import DocstringMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


def test_public_function_with_docstring_not_flagged():
    """Should not flag a public function that has a docstring."""
    ctx = _make_ctx('def good_func():\n    """Has a docstring."""\n    pass\n')
    matcher = DocstringMatcher()
    assert matcher.find(ctx) == []


def test_public_function_without_docstring_flagged():
    """Should flag a public function with no docstring."""
    ctx = _make_ctx("def bad_func():\n    pass\n")
    matcher = DocstringMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "bad_func" in matches[0].matched_value
    assert matches[0].line == 1


def test_private_function_not_flagged():
    """Should not flag private (_-prefixed) functions."""
    ctx = _make_ctx("def _private():\n    pass\n")
    matcher = DocstringMatcher()
    assert matcher.find(ctx) == []


def test_dunder_init_not_flagged():
    """Should not flag __init__ methods."""
    ctx = _make_ctx(
        'class Foo:\n'
        '    def __init__(self):\n'
        '        pass\n'
    )
    matcher = DocstringMatcher()
    assert matcher.find(ctx) == []


def test_method_with_docstring_not_flagged():
    """Should not flag a class method that has a docstring."""
    ctx = _make_ctx(
        'class Foo:\n'
        '    def method(self):\n'
        '        """Has doc."""\n'
        '        pass\n'
    )
    matcher = DocstringMatcher()
    assert matcher.find(ctx) == []


def test_method_without_docstring_flagged():
    """Should flag a class method with no docstring."""
    ctx = _make_ctx(
        'class Foo:\n'
        '    def method(self):\n'
        '        pass\n'
    )
    matcher = DocstringMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "method" in matches[0].matched_value


def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="def bad(): pass")
    matcher = DocstringMatcher()
    assert matcher.find(ctx) == []


def test_multiple_violations():
    """Should flag multiple functions missing docstrings."""
    ctx = _make_ctx(
        "def func_a():\n    pass\n"
        "def func_b():\n    pass\n"
        'def func_c():\n    """Has doc."""\n    pass\n'
    )
    matcher = DocstringMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 2
    names = [m.matched_value for m in matches]
    assert "func_a" in names
    assert "func_b" in names


def test_shared_ctx_none_default():
    """Should work with shared_ctx=None (defensive default)."""
    ctx = _make_ctx("def bad_func():\n    pass\n")
    matcher = DocstringMatcher()
    matches = matcher.find(ctx, shared_ctx=None)
    assert len(matches) == 1


import pytest


@pytest.mark.parametrize("raw", [
    "def alpha():\n    pass\n",
    "def beta():\n    x = 1\n    return x\n",
    "class C:\n    def method(self):\n        return 2\n",
])
def test_docstring_flags_violation(raw):
    """Public callables without a docstring are flagged."""
    assert _make_ctx(raw) and DocstringMatcher().find(_make_ctx(raw))


@pytest.mark.parametrize("raw", [
    'def alpha():\n    """Doc."""\n    pass\n',
    "def _private():\n    pass\n",
    'class C:\n    def method(self):\n        """Doc."""\n        return 2\n',
])
def test_docstring_passes_clean(raw):
    """Documented publics and private callables pass cleanly."""
    assert not DocstringMatcher().find(_make_ctx(raw))
