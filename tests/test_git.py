"""Tests for the Git seam: output parsers and the repo-bound adapter."""
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from enforcer.git import Git, added_lines, parse_name_status


# --- pure parsers -----------------------------------------------------------

@pytest.mark.parametrize("diff,expected", [
    ("@@ -1,2 +3,2 @@\n-old\n+new\n+newer\n", {3, 4}),
    ("@@ -0,0 +5 @@\n+one\n", {5}),
    ("@@ -1 +1 @@\n@@ -10,0 +20,3 @@\n", {1, 20, 21, 22}),
])
def test_added_lines_parses_hunks(diff, expected):
    assert added_lines(diff) == expected


@pytest.mark.parametrize("diff", ["", "no hunk headers here\n", "-only removals\n"])
def test_added_lines_empty_when_no_additions(diff):
    assert added_lines(diff) == set()


@pytest.mark.parametrize("out,expected", [
    ("A\tnew.py\n", (["new.py"], {"new.py": "added"})),
    ("M\tmod.py\n", (["mod.py"], {"mod.py": "modified"})),
    ("D\tdel.py\n", (["del.py"], {"del.py": "deleted"})),
])
def test_parse_name_status_single(out, expected):
    assert parse_name_status(out) == expected


def test_parse_name_status_rename_uses_destination():
    assert parse_name_status("R100\told.py\tnew.py\n") == (["new.py"], {"new.py": "renamed"})


def test_parse_name_status_copy_treated_as_added():
    assert parse_name_status("C100\torig.py\tcopy.py\n") == (["copy.py"], {"copy.py": "added"})


@pytest.mark.parametrize("out", ["", "\n\n", "garbage-no-tab\n"])
def test_parse_name_status_ignores_unparseable(out):
    assert parse_name_status(out) == ([], {})


# --- adapter fail-soft behaviour --------------------------------------------

def _ok(stdout):
    return type("R", (), {"returncode": 0, "stdout": stdout})()


def _fail():
    return type("R", (), {"returncode": 128, "stdout": ""})()


def test_current_branch_returns_name():
    with patch("subprocess.run", return_value=_ok("feature/x\n")):
        assert Git(".").current_branch() == "feature/x"


def test_current_branch_empty_on_git_failure():
    with patch("subprocess.run", return_value=_fail()):
        assert Git(".").current_branch() == ""


def test_current_branch_empty_on_exception():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert Git(".").current_branch() == ""


def test_changed_files_staged():
    with patch("subprocess.run", return_value=_ok("A\ta.py\nM\tb.py\n")):
        assert Git(".").changed_files(staged=True) == (
            ["a.py", "b.py"], {"a.py": "added", "b.py": "modified"})


def test_changed_files_ref():
    with patch("subprocess.run", return_value=_ok("M\tc.py\n")) as run:
        files, _ = Git(".").changed_files(ref="origin/main")
        assert files == ["c.py"]
        assert "origin/main...HEAD" in run.call_args[0][0]


def test_changed_files_neither_mode_is_empty():
    assert Git(".").changed_files() == ([], {})


def test_changed_lines_none_when_no_diff():
    with patch("subprocess.run", return_value=_ok("")):
        assert Git(".").changed_lines("f.py") is None


def test_changed_lines_parses_additions():
    with patch("subprocess.run", return_value=_ok("@@ -1,0 +2,3 @@\n")):
        assert Git(".").changed_lines("f.py") == {2, 3, 4}


# --- commit_subject reads the message file ----------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ENFORCER_COMMIT_MSG_FILE", raising=False)


def test_commit_subject_none_when_absent():
    with tempfile.TemporaryDirectory() as tmp:
        assert Git(tmp).commit_subject() is None


def test_commit_subject_reads_editmsg():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, ".git").mkdir()
        Path(tmp, ".git", "COMMIT_EDITMSG").write_text("feat: x\n\nbody\n")
        assert Git(tmp).commit_subject() == "feat: x"


def test_commit_subject_env_var_overrides_editmsg(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, ".git").mkdir()
        Path(tmp, ".git", "COMMIT_EDITMSG").write_text("stale\n")
        fresh = Path(tmp, "fresh.txt")
        fresh.write_text("fix: fresh\n")
        monkeypatch.setenv("ENFORCER_COMMIT_MSG_FILE", str(fresh))
        assert Git(tmp).commit_subject() == "fix: fresh"


def test_commit_subject_empty_file_is_empty_string():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, ".git").mkdir()
        Path(tmp, ".git", "COMMIT_EDITMSG").write_text("")
        assert Git(tmp).commit_subject() == ""
