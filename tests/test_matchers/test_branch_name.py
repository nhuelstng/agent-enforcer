"""Tests for BranchNameMatcher: enforces branch naming conventions."""
import subprocess
import tempfile
from pathlib import Path
import pytest
from enforcer.matchers.branch_name import BranchNameMatcher
from enforcer.types import FileContext

def _init_git_repo(tmpdir, branch_name="main"):
    subprocess.run(["git", "init", "-b", branch_name], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
    Path(tmpdir, "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)
    if branch_name != "main":
        subprocess.run(["git", "branch", branch_name], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", branch_name], cwd=tmpdir, capture_output=True)

def test_branch_name_matches_pattern():
    """Should not flag when branch matches required pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "feature/ABC-123-add-login")
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_branch_name_does_not_match():
    """Should flag when branch doesn't match required pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "bad-branch-name")
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        matches = matcher.find(ctx, {})
        assert len(matches) == 1
        assert "bad-branch-name" in matches[0].matched_value

def test_branch_name_allows_main():
    """Should allow main/master branches when listed in allow_branches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "main")
        matcher = BranchNameMatcher(pattern=r"^feature/", allow_branches=["main", "master"], workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []

def test_branch_name_detached_head():
    """Should not crash on detached HEAD state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, "main")
        subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=tmpdir, capture_output=True)
        matcher = BranchNameMatcher(pattern=r"^feature/", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        result = matcher.find(ctx, {})
        assert isinstance(result, list)

def test_branch_name_not_a_git_repo():
    """Should not crash when workspace is not a git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        matcher = BranchNameMatcher(pattern=r"^feature/", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {}) == []


@pytest.mark.parametrize("branch", ["bad-branch", "wip", "feature_no_dash"])
def test_branch_name_flags_violation(branch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, branch)
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert matcher.find(ctx, {})


@pytest.mark.parametrize("branch", ["feature/ABC-123-x", "feature/XY-9-z", "main"])
def test_branch_name_passes_clean(branch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_git_repo(tmpdir, branch)
        matcher = BranchNameMatcher(pattern=r"^feature/\w+-\d+-", workspace=tmpdir)
        ctx = FileContext(path=tmpdir, raw=None)
        assert not matcher.find(ctx, {})
