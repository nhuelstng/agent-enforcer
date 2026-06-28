"""Tests for cli.check() extracted helper functions."""
import subprocess
from pathlib import Path
from unittest.mock import patch
from enforcer.cli import _collect_files, _build_shared_ctx, _run_checks


def test_collect_files_staged_empty():
    """Should return empty list when no files staged."""
    with patch("subprocess.check_output", return_value=b""):
        result = _collect_files(staged=True, all_files=False, paths=(), ws=".")
        assert result == []


def test_collect_files_staged_with_files():
    """Should return file list from git diff --cached."""
    with patch("subprocess.check_output", return_value=b"file1.py\nfile2.py\n"):
        result = _collect_files(staged=True, all_files=False, paths=(), ws=".")
        assert result == ["file1.py", "file2.py"]


def test_collect_files_paths():
    """Should return paths directly when paths provided."""
    result = _collect_files(staged=False, all_files=False, paths=("a.py", "b.py"), ws=".")
    assert result == ["a.py", "b.py"]


def test_collect_files_all(tmp_path):
    """Should walk the workspace tree for --all."""
    (tmp_path / "foo.py").write_text("x = 1")
    (tmp_path / "bar.py").write_text("x = 2")
    result = _collect_files(staged=False, all_files=True, paths=(), ws=str(tmp_path))
    assert "foo.py" in result
    assert "bar.py" in result


def test_run_checks_returns_matches():
    """Should return list of Match objects from runner."""
    from enforcer.types import FileContext, Match, Severity
    from enforcer.context import FileContextBuilder
    from enforcer.runner import RuleRunner
    from enforcer.rule import Rule

    rule = Rule(
        id="test",
        severity=Severity.WARN,
        matchers=[],
        file_globs=["**/*.py"],
    )
    runner = RuleRunner([rule], workspace=".")
    builder = FileContextBuilder([rule], workspace=".")
    matches = _run_checks(runner, builder, ["test.py"], {}, ".", staged=False)
    assert isinstance(matches, list)


def test_check_output_writes_file(tmp_path):
    """--output should write results to file instead of stdout."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    outfile = tmp_path / "results.txt"
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--paths", "nonexistent.py", "--output", str(outfile)])
    assert result.exit_code == 0
    assert outfile.exists()
    assert "No issues found" in outfile.read_text()
