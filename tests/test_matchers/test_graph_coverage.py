"""Tests for GraphCoverageMatcher: flags public symbols missing from ONTOLOGY.md."""
import pytest
from enforcer.matchers.graph_coverage import GraphCoverageMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="enforcer/types.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


class TestCleanInGraph:
    """passes when all public symbols are in the rendered graph."""

    @pytest.mark.parametrize("source,symbols_json", [
        ('class Foo:\n    """What: f."""\n    pass\n', '{"symbols": {"enforcer.types.Foo": {}}}'),
        ('def bar():\n    """What: b."""\n    pass\n', '{"symbols": {"enforcer.types.bar": {}}}'),
        ('class Baz:\n    """What: bz."""\n    pass\n', '{"symbols": {"enforcer.types.Baz": {}}}'),
    ])
    def test_clean(self, source, symbols_json):
        ctx = _make_ctx(source)
        matcher = GraphCoverageMatcher()
        shared_ctx = {"__public_symbols__": {"enforcer.types.Foo", "enforcer.types.bar", "enforcer.types.Baz"},
                      "__rendered_ontology__": '{"symbols": {"enforcer.types.Foo": {}, "enforcer.types.bar": {}, "enforcer.types.Baz": {}}}'}
        # Phase 1: find() is a no-op
        matcher.find(ctx, shared_ctx)
        # Phase 2: finalize
        matches = matcher.finalize_duplicates(shared_ctx)
        assert not matches


class TestFlagsMissing:
    """flags public symbols present in code but absent from rendered graph."""

    @pytest.mark.parametrize("missing_symbol", [
        "enforcer.types.Foo",
        "enforcer.types.bar",
        "enforcer.types.Baz",
    ])
    def test_flags_missing(self, missing_symbol):
        ctx = _make_ctx('class Foo:\n    """What: f."""\n    pass\n')
        matcher = GraphCoverageMatcher()
        public_symbols = {"enforcer.types.Foo", "enforcer.types.bar", "enforcer.types.Baz"}
        # Rendered graph is missing one symbol
        all_symbols = {"enforcer.types.Foo", "enforcer.types.bar", "enforcer.types.Baz"}
        all_symbols.discard(missing_symbol)
        symbols_json = '{"symbols": {' + ', '.join(f'"{s}": {{}}' for s in all_symbols) + '}}'
        shared_ctx = {"__public_symbols__": public_symbols, "__rendered_ontology__": symbols_json}
        matcher.find(ctx, shared_ctx)
        matches = matcher.finalize_duplicates(shared_ctx)
        assert len(matches) == 1
        assert missing_symbol in matches[0].matched_value


class TestPrivateIgnored:
    """private symbols are not flagged."""

    @pytest.mark.parametrize("source", [
        'def _private():\n    """What: p."""\n    pass\n',
        'class _Hidden:\n    """What: h."""\n    pass\n',
        'def _helper():\n    """What: hlp."""\n    pass\n',
    ])
    def test_private_not_flagged(self, source):
        ctx = _make_ctx(source)
        matcher = GraphCoverageMatcher()
        shared_ctx = {"__public_symbols__": set(), "__rendered_ontology__": '{"symbols": {}}'}
        matcher.find(ctx, shared_ctx)
        matches = matcher.finalize_duplicates(shared_ctx)
        assert not matches


def test_empty_rendered_ontology_skips():
    """When __rendered_ontology__ is empty, skip silently (no false positives)."""
    ctx = _make_ctx('class Foo:\n    """What: f."""\n    pass\n')
    matcher = GraphCoverageMatcher()
    shared_ctx = {"__public_symbols__": {"enforcer.types.Foo"}, "__rendered_ontology__": ""}
    matcher.find(ctx, shared_ctx)
    matches = matcher.finalize_duplicates(shared_ctx)
    assert not matches


def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="enforcer/types.py", raw="class Foo: pass")
    matcher = GraphCoverageMatcher()
    assert matcher.find(ctx) == []


def test_shared_ctx_none_default():
    """Should work with shared_ctx=None (defensive default)."""
    ctx = _make_ctx('class Foo:\n    """What: f."""\n    pass\n')
    matcher = GraphCoverageMatcher()
    # Should not crash, returns empty
    matches = matcher.find(ctx, shared_ctx=None)
    assert not matches
