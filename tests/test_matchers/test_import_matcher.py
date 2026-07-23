"""Tests for ImportMatcher: detects forbidden cross-layer imports."""
from enforcer.matchers.import_matcher import ImportMatcher
from enforcer.types import FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def test_import_matcher_finds_forbidden_python_import():
    """Should match 'from app.jobs.broker import' in a file."""
    ctx = _make_ctx("from app.jobs.broker import dispatch\n")
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs\."])
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "app.jobs" in matches[0].matched_value

def test_import_matcher_finds_forbidden_import_from():
    """Should match 'import app.jobs.broker' style."""
    ctx = _make_ctx("import app.jobs.broker\n")
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs\."])
    matches = matcher.find(ctx)
    assert len(matches) == 1

def test_import_matcher_no_false_positive_on_allowed_import():
    """Should not match imports that don't match forbidden patterns."""
    ctx = _make_ctx("from app.services.artifact import foo\n")
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs\."])
    matches = matcher.find(ctx)
    assert matches == []

def test_import_matcher_multiple_forbidden():
    """Should find multiple forbidden imports in one file."""
    ctx = _make_ctx(
        "from app.jobs.broker import dispatch\n"
        "from app.jobs.auto_approve import run\n"
        "from app.services import foo\n"
    )
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs\."])
    matches = matcher.find(ctx)
    assert len(matches) == 2

def test_import_matcher_typescript():
    """Should work with TypeScript import statements."""
    ctx = _make_ctx(
        "import { foo } from './api/generated/artifacts/artifacts.service';\n",
        lang=Needs.AST_TS,
    )
    matcher = ImportMatcher(forbidden_patterns=[r"api/generated/"])
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "generated" in matches[0].matched_value

def test_import_matcher_private_symbol_import():
    """Should flag imports of _-prefixed symbols across modules."""
    ctx = _make_ctx("from app.services.plugin_rule_checks import _SECRET_KEY_PATTERN\n")
    matcher = ImportMatcher(forbidden_patterns=[r"_SECRET_KEY_PATTERN"])
    matches = matcher.find(ctx)
    assert len(matches) == 1

def test_import_matcher_multiple_patterns():
    """Should match against multiple forbidden patterns."""
    ctx = _make_ctx(
        "from app.jobs.broker import dispatch\n"
        "from app.seeds.halves import seed\n"
    )
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs\.", r"app\.seeds\."])
    matches = matcher.find(ctx)
    assert len(matches) == 2

def test_import_matcher_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="from app.jobs import x")
    matcher = ImportMatcher(forbidden_patterns=[r"app\.jobs"])
    assert matcher.find(ctx) == []


import pytest


@pytest.mark.parametrize("raw", [
    "from app.jobs.broker import dispatch\n",
    "import app.jobs.worker\n",
    "from app.jobs.auto import run\n",
])
def test_import_flags_violation(raw):
    """Imports matching a forbidden pattern are flagged."""
    assert ImportMatcher(forbidden_patterns=[r"app\.jobs\."]).find(_make_ctx(raw))


@pytest.mark.parametrize("raw", [
    "from app.services.artifact import foo\n",
    "import os\n",
    "from app.models.user import User\n",
])
def test_import_passes_clean(raw):
    """Imports not matching any forbidden pattern pass cleanly."""
    assert not ImportMatcher(forbidden_patterns=[r"app\.jobs\."]).find(_make_ctx(raw))
