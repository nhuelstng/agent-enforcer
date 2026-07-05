"""Tests for DocSyncMatcher: flags if the on-disk generated conventions doc differs from a fresh render."""
import pytest
from pathlib import Path
from enforcer.types import FileContext, Match
from enforcer import Rule, Severity
from enforcer.matchers.regex import RegexMatcher
from enforcer.matchers.doc_sync import DocSyncMatcher


CONFIG_WITH_RULE = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", rationale="Print is bad.")]
WORKSPACE = "."
'''


def _write_config(tmp_path, rules_src):
    """Write a minimal enforcer_config.py to tmp_path."""
    (tmp_path / "enforcer_config.py").write_text(rules_src)


def test_doc_sync_in_sync(tmp_path, monkeypatch):
    """When CONVENTIONS.md matches the rendered doc, no matches."""
    from enforcer.docs import render_rules_doc
    from enforcer.config import load_config

    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    config = load_config("enforcer_config.py")
    fresh = render_rules_doc(config.rules, workspace=config.workspace)
    (tmp_path / "CONVENTIONS.md").write_text(fresh)

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_doc__": fresh})
    assert matches == []


class TestDocSyncFlags:
    """flags when on-disk doc differs from rendered doc."""

    @pytest.mark.parametrize("on_disk_content,rendered_doc", [
        ("# Stale content\n", "# Fresh render\n"),
        ("# Wrong\n", "# Right\n"),
        ("old text", "new text"),
    ])
    def test_flags_stale(self, tmp_path, monkeypatch, on_disk_content, rendered_doc):
        _write_config(tmp_path, CONFIG_WITH_RULE)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CONVENTIONS.md").write_text(on_disk_content)

        matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
        ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
        matches = matcher.find(ctx, {"__rendered_doc__": rendered_doc})
        assert len(matches) == 1
        assert "stale" in matches[0].message.lower()


class TestDocSyncClean:
    """passes when on-disk doc matches rendered doc."""

    @pytest.mark.parametrize("content", [
        "# Fresh render\n",
        "# Right\n",
        "matching text",
    ])
    def test_success_in_sync(self, tmp_path, monkeypatch, content):
        _write_config(tmp_path, CONFIG_WITH_RULE)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CONVENTIONS.md").write_text(content)

        matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
        ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
        matches = matcher.find(ctx, {"__rendered_doc__": content})
        assert not matches


def test_doc_sync_missing_file_flags_stale(tmp_path, monkeypatch):
    """When CONVENTIONS.md doesn't exist, emits a match (treated as stale)."""
    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_doc__": "# Fresh render\n"})
    assert len(matches) == 1


def test_doc_sync_empty_shared_ctx_flags_stale(tmp_path, monkeypatch):
    """When shared_ctx has no __rendered_doc__ (empty default), flags stale if file exists."""
    _write_config(tmp_path, CONFIG_WITH_RULE)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CONVENTIONS.md").write_text("# Some content\n")

    matcher = DocSyncMatcher(doc_path="CONVENTIONS.md")
    ctx = FileContext(path="enforcer_config.py", raw="x = 1\n")
    matches = matcher.find(ctx, {})
    assert len(matches) == 1
