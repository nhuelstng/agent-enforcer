"""Tests for SharedCtxKeyAllowlistMatcher: flags undeclared shared_ctx key accesses."""
import pytest
from enforcer.matchers.shared_ctx_allowlist import SharedCtxKeyAllowlistMatcher
from enforcer.types import FileContext, Needs

_ALLOWED = {"__import_graph__", "__rendered_doc__", "__change__"}


class TestFlagsUndeclared:
    """flags shared_ctx accesses for keys not in the allowlist."""

    @pytest.mark.parametrize("source,expected_key", [
        ('shared_ctx.get("__public_symbols__")\n', "__public_symbols__"),
        ('shared_ctx["__rendered_ontology__"]\n', "__rendered_ontology__"),
        ('x = shared_ctx.get("__llm_enabled__")\n', "__llm_enabled__"),
    ])
    def test_flags_undeclared(self, source, expected_key):
        ctx = FileContext(path="enforcer/matchers/foo.py", raw=source)
        matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert expected_key in matches[0].matched_value


class TestCleanDeclared:
    """passes when all shared_ctx accesses use declared keys."""

    @pytest.mark.parametrize("source", [
        'shared_ctx.get("__import_graph__")\n',
        'shared_ctx["__rendered_doc__"]\n',
        'x = shared_ctx.get("__change__")\n',
    ])
    def test_clean(self, source):
        ctx = FileContext(path="enforcer/matchers/foo.py", raw=source)
        matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
        matches = matcher.find(ctx)
        assert not matches


class TestNoAccess:
    """files with no shared_ctx access produce no matches."""

    @pytest.mark.parametrize("source", [
        'x = 1\n',
        'def foo():\n    return "hello"\n',
        '# just a comment\n',
    ])
    def test_no_access(self, source):
        ctx = FileContext(path="enforcer/matchers/foo.py", raw=source)
        matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
        matches = matcher.find(ctx)
        assert not matches


class TestMultipleAccess:
    """multiple undeclared accesses each produce a match."""

    @pytest.mark.parametrize("source", [
        ('shared_ctx.get("__a__")\nshared_ctx.get("__b__")\n'),
        ('shared_ctx["__x__"]\nshared_ctx["__y__"]\n'),
        ('shared_ctx.get("__a__")\nshared_ctx["__b__"]\n'),
    ])
    def test_multiple_flags(self, source):
        ctx = FileContext(path="enforcer/matchers/foo.py", raw=source)
        matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
        matches = matcher.find(ctx)
        assert len(matches) == 2


def test_no_raw_returns_empty():
    """Should return empty list if raw is None."""
    ctx = FileContext(path="enforcer/matchers/foo.py", raw=None)
    matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
    assert matcher.find(ctx) == []


def test_shared_ctx_none_default():
    """Should work with shared_ctx=None (defensive default)."""
    ctx = FileContext(path="enforcer/matchers/foo.py", raw='shared_ctx.get("__undeclared__")\n')
    matcher = SharedCtxKeyAllowlistMatcher(allowed_keys=_ALLOWED)
    matches = matcher.find(ctx, shared_ctx=None)
    assert len(matches) == 1
