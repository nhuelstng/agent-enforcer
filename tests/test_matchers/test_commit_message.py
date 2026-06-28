"""Tests for CommitMessageMatcher: enforces commit message format."""
import subprocess
import tempfile
from pathlib import Path
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.types import FileContext

def _init_git_with_commit_msg(tmpdir, msg):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    Path(tmpdir, ".git/COMMIT_EDITMSG").write_text(msg)

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
