"""Tests for ConstantNamingMatcher: flags module-level constants not named UPPER_CASE."""
import pytest
from enforcer.matchers.constant_naming import ConstantNamingMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_LOWER_CONST = 'my_const = 42\n'
_CAMEL_CONST = 'myConst = 42\n'
_UPPER_CONST = 'MY_CONST = 42\n'
_PRIVATE_CONST = '_private = 42\n'
_MIXED = '''\
UPPER_OK = 1
lower_bad = 2
Also_Bad = 3
'''

_EMPTY = ''


class TestConstantNamingFlags:
    """flags module-level non-private constants not in UPPER_CASE."""

    @pytest.mark.parametrize("source", [
        _LOWER_CONST,
        _CAMEL_CONST,
    ])
    def test_flags_bad_naming(self, source):
        ctx = _make_ctx(source)
        matches = ConstantNamingMatcher().find(ctx)
        assert len(matches) == 1

    def test_mixed_flags_only_bad(self):
        ctx = _make_ctx(_MIXED)
        matches = ConstantNamingMatcher().find(ctx)
        assert len(matches) == 2
        names = [m.matched_value for m in matches]
        assert "lower_bad" in names
        assert "Also_Bad" in names


class TestConstantNamingClean:
    """does not flag UPPER_CASE, private, or empty files."""

    @pytest.mark.parametrize("source", [
        _UPPER_CONST,
        _PRIVATE_CONST,
        _EMPTY,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert ConstantNamingMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert ConstantNamingMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="x = 1\n")
        assert ConstantNamingMatcher().find(ctx) == []
