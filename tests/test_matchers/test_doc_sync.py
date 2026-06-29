import pytest
from pathlib import Path
from enforcer.types import FileContext, Match
from enforcer import Rule, Severity
from enforcer.matchers.regex import RegexMatcher


def _write_config(tmp_path, rules_src):
    """Write a minimal enforcer_config.py to tmp_path."""
    (tmp_path / "enforcer_config.py").write_text(rules_src)


CONFIG_WITH_RULE = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
WORKSPACE = "."
'''


def test_doc_sync_in_sync(tmp_path, monkeypatch):
    """When CONVENTIONS.md matches a fresh render, no matches."""
    from enforcer.matchers.doc_sync import DocSyncMatcher
    from enforcer.docs import render_rules_doc
    from enforcer.config import load_config

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config = load_config("enforcer_config.py")
    fresh = render_rules_doc(config.rules, workspace=config.workspace)
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": config.rules, "__workspace__": "."})
    assert matches == []


def test_doc_sync_stale(tmp_path, monkeypatch):
    """When CONVENTIONS.md content differs, emits a match."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "CONVENTIONS.md").write_text("# Stale content\n")

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": None})  # force fallback to load_config
    assert len(matches) == 1
    assert "stale" in matches[0].message.lower()


def test_doc_sync_missing_file(tmp_path, monkeypatch):
    """When CONVENTIONS.md doesn't exist, emits a match (treated as stale)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rules__": None})
    assert len(matches) == 1


def test_doc_sync_uses_shared_ctx_rules(tmp_path, monkeypatch):
    """When shared_ctx has __rules__, does not call load_config."""
    from enforcer.matchers.doc_sync import DocSyncMatcher
    from enforcer.docs import render_rules_doc

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config_rules = [Rule(id="test", severity=Severity.ERROR, matchers=[], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
    fresh = render_rules_doc(config_rules, workspace=".")
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")

    # Should use shared_ctx rules, not load_config
    matches = matcher.find(ctx, {"__rules__": config_rules, "__workspace__": "."})
    assert matches == []


def test_doc_sync_load_config_error_propagates(tmp_path, monkeypatch):
    """When load_config raises, error propagates (not swallowed)."""
    from enforcer.matchers.doc_sync import DocSyncMatcher

    monkeypatch.chdir(tmp_path)
    # No enforcer_config.py exists → load_config will raise
    matcher = DocSyncMatcher(config_path="nonexistent.py", doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")

    with pytest.raises(Exception):
        matcher.find(ctx, {"__rules__": None})
