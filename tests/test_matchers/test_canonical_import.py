"""Tests for CanonicalImportMatcher: enforces symbols imported from canonical module."""
import pytest
from enforcer.matchers.canonical_import import CanonicalImportMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


@pytest.mark.parametrize("source", [
    "from enforcer.rule import _glob_match\n",
    "from enforcer.rule import _glob_match as gm\n",
    "from enforcer.rule import Rule, _glob_match\n",
    "from enforcer.rule import Rule as r, _glob_match as gm\n",
])
def test_canonical_import_fail(source):
    """Should flag imports of canonical-mapped symbols from non-canonical modules."""
    canonical = {"_glob_match": "enforcer.glob_util"}
    matches = CanonicalImportMatcher(canonical=canonical).find(_make_ctx(source))
    assert matches


@pytest.mark.parametrize("source", [
    "from enforcer.glob_util import _glob_match\n",
    "from enforcer.rule import Rule\n",
    "import enforcer.rule\n",
    "from . import foo\n",
    "from .rule import _glob_match\n",
])
def test_canonical_import_success(source):
    """Should not flag imports from canonical modules, unknown symbols, or relative imports."""
    canonical = {"_glob_match": "enforcer.glob_util"}
    matches = CanonicalImportMatcher(canonical=canonical).find(_make_ctx(source))
    assert matches == []


def test_canonical_import_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="from enforcer.rule import _glob_match")
    canonical = {"_glob_match": "enforcer.glob_util"}
    assert CanonicalImportMatcher(canonical=canonical).find(ctx) == []
