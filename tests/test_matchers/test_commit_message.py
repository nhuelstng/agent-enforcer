"""Tests for CommitMessageMatcher: enforces commit message format."""
import subprocess
import tempfile
from pathlib import Path
import pytest
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.types import FileContext


@pytest.fixture(autouse=True)
def _clean_commit_msg_env(monkeypatch):
    """Ensure ENFORCER_COMMIT_MSG_FILE does not leak across tests."""
    monkeypatch.delenv("ENFORCER_COMMIT_MSG_FILE", raising=False)


def _init_git_with_commit_msg(tmpdir, msg, monkeypatch, use_env_var=True):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    if use_env_var:
        msg_file = Path(tmpdir, ".git", "ENFORCER_MSG_FILE")
        msg_file.write_text(msg)
        monkeypatch.setenv("ENFORCER_COMMIT_MSG_FILE", str(msg_file))
    else:
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text(msg)
        monkeypatch.delenv("ENFORCER_COMMIT_MSG_FILE", raising=False)


def test_commit_message_matches_conventional_commits(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: add login page\n\nCloses ABC-123", monkeypatch)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_does_not_match(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "updated stuff", monkeypatch)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        matches = matcher.find(ctx, {})
        assert len(matches) == 1
        assert "updated stuff" in matches[0].matched_value

def test_commit_message_multiline(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "fix: handle null\n\nBody text here\nMore body", monkeypatch)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_no_msg_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        monkeypatch.delenv("ENFORCER_COMMIT_MSG_FILE", raising=False)
        matcher = CommitMessageMatcher(pattern=r"^feat:", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_custom_pattern(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "ABC-123: add feature", monkeypatch)
        matcher = CommitMessageMatcher(pattern=r"^\w+-\d+:\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_merge_commit_skipped(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "Merge branch 'feature' into main", monkeypatch)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_falls_back_to_commit_editmsg(monkeypatch):
    """When ENFORCER_COMMIT_MSG_FILE is not set, fall back to COMMIT_EDITMSG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: from editmsg", monkeypatch, use_env_var=False)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_env_var_takes_priority(monkeypatch):
    """ENFORCER_COMMIT_MSG_FILE takes priority over stale COMMIT_EDITMSG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: current message", monkeypatch, use_env_var=True)
        # Write stale message to COMMIT_EDITMSG (simulates -m commit during hook)
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text("old: stale message")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []


_CM_PATTERN = r"^(feat|fix|docs|refactor|test|chore):\s+.+"


@pytest.mark.parametrize("msg", ["updated stuff", "wip changes", "random text here"])
def test_commit_message_flags_violation(msg, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, msg, monkeypatch)
        matcher = CommitMessageMatcher(pattern=_CM_PATTERN, workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {})


@pytest.mark.parametrize("msg", ["feat: add x", "fix: bug y", "Merge branch 'z'"])
def test_commit_message_passes_clean(msg, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, msg, monkeypatch)
        matcher = CommitMessageMatcher(pattern=_CM_PATTERN, workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert not matcher.find(ctx, {})
