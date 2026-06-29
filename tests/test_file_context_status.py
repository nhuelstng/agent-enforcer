"""Tests for FileContext.status field and ChangeContext dataclass."""
from dataclasses import dataclass, replace
from pathlib import Path
from enforcer.types import FileContext, ChangeContext


def test_file_context_has_status_default_modified():
    ctx = FileContext(path="foo.py", raw="x = 1")
    assert ctx.status == "modified"


def test_file_context_status_can_be_set():
    ctx = FileContext(path="foo.py", raw="x = 1", status="added")
    assert ctx.status == "added"


def test_file_context_status_via_replace():
    ctx = FileContext(path="foo.py", raw="x = 1")
    ctx2 = replace(ctx, status="deleted")
    assert ctx2.status == "deleted"
    assert ctx.status == "modified"


def test_change_context_defaults():
    cc = ChangeContext()
    assert cc.commit_msg == ""
    assert cc.branch == ""
    assert cc.created == []
    assert cc.modified == []
    assert cc.deleted == []
    assert cc.renamed == []


def test_change_context_created_dirs():
    cc = ChangeContext(created=["src/new/foo.py", "src/new/bar.py", "README.md"])
    dirs = cc.created_dirs
    assert "src/new" in dirs
    assert "" in dirs  # README.md has no parent dir


def test_change_context_deleted_dirs():
    cc = ChangeContext(deleted=["old/gone.py"])
    assert "old" in cc.deleted_dirs


def test_change_context_empty_dirs():
    cc = ChangeContext()
    assert cc.created_dirs == set()
    assert cc.deleted_dirs == set()
