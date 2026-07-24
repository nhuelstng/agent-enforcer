"""Tests for TypeHintMatcher: flags public functions missing return type annotations."""
import pytest
from enforcer.matchers.type_hint import TypeHintMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_NO_RETURN = '''\
def public_func(x):
    return x

def _private_func(x):
    return x
'''

_WITH_RETURN = '''\
def public_func(x) -> int:
    return x

def _private_func(x) -> int:
    return x
'''

_MIXED = '''\
def with_hint(x) -> str:
    return x

def without_hint(x):
    return x
'''

_INIT_ONLY = '''\
class Foo:
    def __init__(self):
        pass
'''


class TestTypeHintFlags:
    """flags public functions missing return type annotations."""

    @pytest.mark.parametrize("source", [
        _NO_RETURN,
        _MIXED,
    ])
    def test_flags_missing_return(self, source):
        ctx = _make_ctx(source)
        matches = TypeHintMatcher().find(ctx)
        assert len(matches) >= 1
        assert all(m.matched_value == "without_hint" or m.matched_value == "public_func" for m in matches)

    def test_flags_only_public_no_return(self):
        ctx = _make_ctx(_NO_RETURN)
        matches = TypeHintMatcher().find(ctx)
        assert len(matches) == 1
        assert matches[0].matched_value == "public_func"


class TestTypeHintClean:
    """does not flag functions with return hints or private functions."""

    @pytest.mark.parametrize("source", [
        _WITH_RETURN,
        _INIT_ONLY,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert TypeHintMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert TypeHintMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="def f(): pass\n")
        assert TypeHintMatcher().find(ctx) == []


@pytest.mark.parametrize("source", [
    "def a(x):\n    return x\n",
    "def b(x):\n    return x\ndef c(y):\n    return y\n",
    "def public(x):\n    return x\ndef _priv(x) -> int:\n    return x\n",
])
def test_type_hint_flags_violation(source):
    """Flags public functions lacking a return annotation (>=3 parametrized cases)."""
    assert TypeHintMatcher().find(_make_ctx(source))


@pytest.mark.parametrize("source", [
    "def a(x) -> int:\n    return x\n",
    "def _priv(x):\n    return x\n",
    "def b(x) -> str:\n    return x\ndef c(y) -> int:\n    return y\n",
])
def test_type_hint_passes_clean(source):
    """No match when public functions carry return hints or are private (>=3 cases)."""
    assert not TypeHintMatcher().find(_make_ctx(source))
