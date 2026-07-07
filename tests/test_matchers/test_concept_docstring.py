"""Tests for ConceptDocstringMatcher: flags public symbols missing 'What:' docstring section."""
import pytest
from enforcer.matchers.concept_docstring import ConceptDocstringMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


class TestFlagsMissing:
    """flags public symbols that lack a 'What:' section in their docstring."""

    @pytest.mark.parametrize("source", [
        'class Foo:\n    """A class without What."""\n    pass\n',
        'def bar():\n    """A function without What."""\n    pass\n',
        'class Baz:\n    pass\n',
    ])
    def test_flags(self, source):
        ctx = _make_ctx(source)
        matcher = ConceptDocstringMatcher()
        matches = matcher.find(ctx)
        assert len(matches) >= 1


class TestCleanHasWhat:
    """passes when public symbols have a 'What:' section."""

    @pytest.mark.parametrize("source", [
        'class Foo:\n    """A class.\n\n    What: does foo.\n    """\n    pass\n',
        'def bar():\n    """What: does bar."""\n    pass\n',
        'class Baz:\n    """What: baz."""\n    pass\n',
    ])
    def test_clean(self, source):
        ctx = _make_ctx(source)
        matcher = ConceptDocstringMatcher()
        matches = matcher.find(ctx)
        assert not matches


class TestPrivateIgnored:
    """private (_-prefixed) symbols are not flagged even without What:."""

    @pytest.mark.parametrize("source", [
        'def _private():\n    """no what."""\n    pass\n',
        'class _Hidden:\n    pass\n',
        'def _helper():\n    pass\n',
    ])
    def test_private_not_flagged(self, source):
        ctx = _make_ctx(source)
        matcher = ConceptDocstringMatcher()
        matches = matcher.find(ctx)
        assert not matches


def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="class Foo: pass")
    matcher = ConceptDocstringMatcher()
    assert matcher.find(ctx) == []


def test_shared_ctx_none_default():
    """Should work with shared_ctx=None (defensive default)."""
    ctx = _make_ctx('class Foo:\n    """no what."""\n    pass\n')
    matcher = ConceptDocstringMatcher()
    matches = matcher.find(ctx, shared_ctx=None)
    assert len(matches) == 1
