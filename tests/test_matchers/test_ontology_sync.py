"""Tests for OntologySyncMatcher: flags if on-disk ONTOLOGY.md differs from fresh render."""
import pytest
from pathlib import Path
from enforcer.types import FileContext
from enforcer.matchers.ontology_sync import OntologySyncMatcher


class TestOntologySyncFlags:
    """flags when on-disk graph differs from rendered graph."""

    @pytest.mark.parametrize("on_disk,rendered", [
        ("# Stale\n", "# Fresh\n"),
        ("# Wrong\n", "# Right\n"),
        ("old text", "new text"),
    ])
    def test_flags_stale(self, tmp_path, monkeypatch, on_disk, rendered):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "ONTOLOGY.md").write_text(on_disk)
        matcher = OntologySyncMatcher(graph_path="ONTOLOGY.md")
        ctx = FileContext(path="enforcer/types.py", raw="x = 1\n")
        matches = matcher.find(ctx, {"__rendered_ontology__": rendered})
        assert len(matches) == 1
        assert "stale" in matches[0].message.lower()


class TestOntologySyncClean:
    """passes when on-disk graph matches rendered graph."""

    @pytest.mark.parametrize("content", [
        "# Fresh render\n",
        "# Right\n",
        "matching text",
    ])
    def test_success_in_sync(self, tmp_path, monkeypatch, content):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "ONTOLOGY.md").write_text(content)
        matcher = OntologySyncMatcher(graph_path="ONTOLOGY.md")
        ctx = FileContext(path="enforcer/types.py", raw="x = 1\n")
        matches = matcher.find(ctx, {"__rendered_ontology__": content})
        assert not matches


def test_missing_file_flags_stale(tmp_path, monkeypatch):
    """When ONTOLOGY.md doesn't exist, emits a match."""
    monkeypatch.chdir(tmp_path)
    matcher = OntologySyncMatcher(graph_path="ONTOLOGY.md")
    ctx = FileContext(path="enforcer/types.py", raw="x = 1\n")
    matches = matcher.find(ctx, {"__rendered_ontology__": "# Fresh\n"})
    assert len(matches) == 1


def test_empty_shared_ctx_flags_stale(tmp_path, monkeypatch):
    """When shared_ctx has no __rendered_ontology__ (empty default), flags stale if file exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ONTOLOGY.md").write_text("# Some content\n")
    matcher = OntologySyncMatcher(graph_path="ONTOLOGY.md")
    ctx = FileContext(path="enforcer/types.py", raw="x = 1\n")
    matches = matcher.find(ctx, {})
    assert len(matches) == 1


def test_shared_ctx_none_default(tmp_path, monkeypatch):
    """Should work with shared_ctx=None (defensive default)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ONTOLOGY.md").write_text("# Some content\n")
    matcher = OntologySyncMatcher(graph_path="ONTOLOGY.md")
    ctx = FileContext(path="enforcer/types.py", raw="x = 1\n")
    matches = matcher.find(ctx, shared_ctx=None)
    assert len(matches) == 1
