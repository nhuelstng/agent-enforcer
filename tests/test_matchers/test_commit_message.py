"""Tests for CommitMessageMatcher: enforces commit message format."""
import os
import subprocess
import tempfile
from pathlib import Path
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.types import FileContext

def _init_git_with_commit_msg(tmpdir, msg, use_env_var=True):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    if use_env_var:
        msg_file = Path(tmpdir, ".git", "ENFORCER_MSG_FILE")
        msg_file.write_text(msg)
        os.environ["ENFORCER_COMMIT_MSG_FILE"] = str(msg_file)
    else:
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text(msg)
        os.environ.pop("ENFORCER_COMMIT_MSG_FILE", None)

def test_commit_message_matches_conventional_commits():
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: add login page\n\nCloses ABC-123")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_does_not_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "updated stuff")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        matches = matcher.find(ctx, {})
        assert len(matches) == 1
        assert "updated stuff" in matches[0].matched_value

def test_commit_message_multiline():
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "fix: handle null\n\nBody text here\nMore body")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_no_msg_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.environ.pop("ENFORCER_COMMIT_MSG_FILE", None)
        matcher = CommitMessageMatcher(pattern=r"^feat:", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_custom_pattern():
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "ABC-123: add feature")
        matcher = CommitMessageMatcher(pattern=r"^\w+-\d+:\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_merge_commit_skipped():
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "Merge branch 'feature' into main")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_falls_back_to_commit_editmsg():
    """When ENFORCER_COMMIT_MSG_FILE is not set, fall back to COMMIT_EDITMSG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: from editmsg", use_env_var=False)
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_commit_message_env_var_takes_priority():
    """ENFORCER_COMMIT_MSG_FILE takes priority over stale COMMIT_EDITMSG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_with_commit_msg(tmpdir, "feat: current message", use_env_var=True)
        # Write stale message to COMMIT_EDITMSG (simulates -m commit during hook)
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text("old: stale message")
        matcher = CommitMessageMatcher(pattern=r"^(feat|fix):\s+.+", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []
