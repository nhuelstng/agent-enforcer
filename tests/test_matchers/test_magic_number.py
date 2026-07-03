"""Tests for MagicNumberMatcher: flags magic numbers outside constant assignments."""
import pytest
from enforcer.matchers.magic_number import MagicNumberMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_MAGIC_INT = 'def f():\n    x = 42\n'
_ALLOWED_INT = 'def f():\n    x = 3\n'
_CONSTANT_ASSIGN = 'MAX_RETRIES = 100\n'
_FUNC_BODY_MAGIC = 'def f():\n    timeout = 300\n    return timeout\n'
_FLOAT_MAGIC = 'def f():\n    rate = 3.14\n'
_ALLOWED_NEG = 'def f():\n    x = -5\n'
_MAGIC_NEG = 'def f():\n    x = -100\n'
_ALLOWED_ZERO = 'def f():\n    x = 0\n'


class TestMagicNumberFlags:
    """flags magic numbers outside constant assignments."""

    @pytest.mark.parametrize("source", [
        _MAGIC_INT,
        _FLOAT_MAGIC,
        _MAGIC_NEG,
    ])
    def test_flags_magic_numbers(self, source):
        ctx = _make_ctx(source)
        matches = MagicNumberMatcher().find(ctx)
        assert len(matches) >= 1

    def test_func_body_magic_flagged(self):
        ctx = _make_ctx(_FUNC_BODY_MAGIC)
        matches = MagicNumberMatcher().find(ctx)
        assert len(matches) == 1
        assert matches[0].matched_value == "300"


class TestMagicNumberClean:
    """does not flag allowed integers or constant assignments."""

    @pytest.mark.parametrize("source", [
        _ALLOWED_INT,
        _CONSTANT_ASSIGN,
        _ALLOWED_NEG,
        _ALLOWED_ZERO,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert MagicNumberMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert MagicNumberMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="x = 1\n")
        assert MagicNumberMatcher().find(ctx) == []
