"""Tests for git diff --name-status parsing and ChangeContext building in CLI."""
import subprocess
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from enforcer.cli import _parse_name_status, _build_change_context


def test_parse_name_status_added():
    output = "A\tnew_file.py\n"
    result = _parse_name_status(output)
    assert result == (["new_file.py"], {"new_file.py": "added"})


def test_parse_name_status_modified():
    output = "M\tmodified.py\n"
    result = _parse_name_status(output)
    assert result == (["modified.py"], {"modified.py": "modified"})


def test_parse_name_status_deleted():
    output = "D\tdeleted.py\n"
    result = _parse_name_status(output)
    assert result == (["deleted.py"], {"deleted.py": "deleted"})


def test_parse_name_status_renamed():
    output = "R100\told.py\tnew.py\n"
    result = _parse_name_status(output)
    assert result == (["new.py"], {"new.py": "renamed"})


def test_parse_name_status_copy_treated_as_added():
    output = "C100\torig.py\tcopy.py\n"
    result = _parse_name_status(output)
    assert result == (["copy.py"], {"copy.py": "added"})


def test_parse_name_status_multiple():
    output = "A\tnew.py\nM\tmod.py\nD\tdel.py\nR100\told.py\tnew.py\n"
    files, status_map = _parse_name_status(output)
    assert "new.py" in files
    assert "mod.py" in files
    assert "del.py" in files
    assert status_map["mod.py"] == "modified"
    assert status_map["del.py"] == "deleted"
    # renamed overwrites the new path status (R100\told.py\tnew.py — last wins)
    assert status_map["new.py"] == "renamed"


def test_parse_name_status_empty_output():
    result = _parse_name_status("")
    assert result == ([], {})


def test_parse_name_status_skips_blank_lines():
    output = "A\tfoo.py\n\n\nM\tbar.py\n"
    files, status_map = _parse_name_status(output)
    assert files == ["foo.py", "bar.py"]
    assert status_map == {"foo.py": "added", "bar.py": "modified"}


def test_build_change_context_reads_commit_msg():
    """_build_change_context reads commit message from .git/COMMIT_EDITMSG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        os.makedirs(os.path.join(tmpdir, ".git/refs/heads"), exist_ok=True)
        Path(tmpdir, ".git/HEAD").write_text("ref: refs/heads/feature/test\n")
        Path(tmpdir, ".git/refs/heads/feature").mkdir(parents=True, exist_ok=True)
        Path(tmpdir, ".git/refs/heads/feature/test").write_text("0" * 40)
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text("feat: add new thing\n\nBody text\n")

        status_map = {"new.py": "added", "mod.py": "modified", "del.py": "deleted", "ren.py": "renamed"}
        cc = _build_change_context(tmpdir, status_map)
        assert cc.commit_msg == "feat: add new thing"
        assert cc.created == ["new.py"]
        assert cc.modified == ["mod.py"]
        assert cc.deleted == ["del.py"]
        assert cc.renamed == ["ren.py"]


def test_build_change_context_skips_merge_commit_msg():
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text("Merge branch 'feature' into master\n")

        cc = _build_change_context(tmpdir, {})
        assert cc.commit_msg == ""


def test_build_change_context_no_commit_editmsg():
    with tempfile.TemporaryDirectory() as tmpdir:
        cc = _build_change_context(tmpdir, {})
        assert cc.commit_msg == ""


def test_build_change_context_empty_status_map():
    with tempfile.TemporaryDirectory() as tmpdir:
        cc = _build_change_context(tmpdir, {})
        assert cc.created == []
        assert cc.modified == []
        assert cc.deleted == []
        assert cc.renamed == []
