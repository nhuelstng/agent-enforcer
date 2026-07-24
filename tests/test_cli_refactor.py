"""Tests for cli.check() extracted helper functions."""
import subprocess
from pathlib import Path
from unittest.mock import patch
from enforcer.check_runner import collect_files as _collect_files, run_checks as _run_checks, CheckOptions


def test_collect_files_staged_empty():
    """Should return empty list when no files staged."""
    with patch("subprocess.check_output", return_value=b""):
        result = _collect_files(staged=True, all_files=False, paths=(), ws=".")
        assert result == ([], {})


def test_collect_files_staged_with_files():
    """Should return file list from git diff --cached."""
    with patch("subprocess.check_output", return_value=b"M\tfile1.py\nM\tfile2.py\n"):
        result = _collect_files(staged=True, all_files=False, paths=(), ws=".")
        assert result == (["file1.py", "file2.py"], {"file1.py": "modified", "file2.py": "modified"})


def test_collect_files_paths():
    """Should return paths directly when paths provided."""
    result = _collect_files(staged=False, all_files=False, paths=("a.py", "b.py"), ws=".")
    assert result == (["a.py", "b.py"], {})


def test_collect_files_all(tmp_path):
    """Should walk the workspace tree for --all."""
    (tmp_path / "foo.py").write_text("x = 1")
    (tmp_path / "bar.py").write_text("x = 2")
    result = _collect_files(staged=False, all_files=True, paths=(), ws=str(tmp_path))
    files, status_map = result
    assert "foo.py" in files
    assert "bar.py" in files
    assert status_map == {}


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
    matches = _run_checks(runner, builder, ["test.py"], {}, CheckOptions(staged=False))
    assert isinstance(matches, list)


def test_check_output_writes_file(tmp_path):
    """--output should write results to file inside workspace."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("enforcer_config.py").write_text("from enforcer import Rule, Severity\nRULES = []\nWORKSPACE = '.'\n")
        outfile = "results.txt"
        result = runner.invoke(cli, ["check", "--paths", "nonexistent.py", "--output", outfile, "--config", "enforcer_config.py"])
        assert result.exit_code == 0
        assert Path(outfile).exists()
        assert "No issues found" in Path(outfile).read_text()


def test_parse_diff_changed_lines_with_ref():
    """Should use <ref>...HEAD when ref is provided."""
    from enforcer.check_runner import _parse_diff_changed_lines
    diff_output = b"@@ -1,2 +3,2 @@\n-old\n+new\n+newer\n"
    with patch("subprocess.run", return_value=type("R", (), {"returncode": 0, "stdout": diff_output.decode()})()) as mock_run:
        result = _parse_diff_changed_lines(".", "file.py", ref="origin/master")
        assert result == {3, 4}
        # Verify git command used ref, not --cached
        cmd = mock_run.call_args[0][0]
        assert "origin/master...HEAD" in cmd
        assert "--cached" not in cmd


def test_parse_diff_changed_lines_staged_no_ref():
    """Should use --cached when ref is None."""
    from enforcer.check_runner import _parse_diff_changed_lines
    diff_output = b"@@ -1,0 +2,0 @@\n"
    with patch("subprocess.run", return_value=type("R", (), {"returncode": 0, "stdout": diff_output.decode()})()) as mock_run:
        _parse_diff_changed_lines(".", "file.py", ref=None)
        cmd = mock_run.call_args[0][0]
        assert "--cached" in cmd


def test_collect_files_staged_filters_blank_lines():
    """Should drop empty entries when git output has blank lines mid-stream."""
    with patch("subprocess.check_output", return_value=b"M\ta.py\n\nM\tb.py\n"):
        result = _collect_files(staged=True, all_files=False, paths=(), ws=".")
    assert result == (["a.py", "b.py"], {"a.py": "modified", "b.py": "modified"})


def test_collect_files_base_ref_filters_blank_lines():
    """Should drop empty entries when git diff base_ref output has blank lines."""
    with patch("subprocess.check_output", return_value=b"M\ta.py\n\nM\tb.py\n"):
        result = _collect_files(staged=False, all_files=False, paths=(), ws=".", base_ref="origin/master")
    assert result == (["a.py", "b.py"], {"a.py": "modified", "b.py": "modified"})


def test_collect_files_base_ref():
    """Should return file list from git diff <ref>...HEAD when base_ref provided."""
    with patch("subprocess.check_output", return_value=b"M\tchanged.py\nM\tother.py\n"):
        result = _collect_files(staged=False, all_files=False, paths=(), ws=".", base_ref="origin/master")
    assert result == (["changed.py", "other.py"], {"changed.py": "modified", "other.py": "modified"})


def test_run_checks_with_diff_ref():
    """Should set changed_lines when diff_ref is provided."""
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
    with patch("enforcer.check_runner._parse_diff_changed_lines", return_value={5, 6}) as mock_parse:
        matches = _run_checks(runner, builder, ["test.py"], {}, CheckOptions(staged=False, diff_ref="origin/master"))
    assert isinstance(matches, list)
    mock_parse.assert_called_once_with(".", "test.py", ref="origin/master")


def test_check_base_ref_mutual_exclusion():
    """--base-ref with --staged should error."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--staged", "--base-ref", "origin/master"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output.lower()


def test_check_paths_with_base_ref_excluded():
    """--paths with --base-ref should error."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--paths", "foo.py", "--base-ref", "origin/master"])
    assert result.exit_code == 2
    assert "--paths cannot be combined" in result.output
