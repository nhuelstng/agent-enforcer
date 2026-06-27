"""Tests for .enforcerignore integration with CLI check command."""
import tempfile
from pathlib import Path
from click.testing import CliRunner
from enforcer.cli import cli


def test_enforcerignore_skips_files():
    """CLI should skip files matching .enforcerignore patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "app.py").write_text("print('hello')\n")
        Path(tmpdir, "ignored.py").write_text("print('ignored')\n")
        Path(tmpdir, ".enforcerignore").write_text("ignored.py\n")

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "app.py", "--paths", "ignored.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        # Should only flag app.py, not ignored.py
        assert "app.py" in result.output
        assert "ignored.py" not in result.output


def test_enforcerignore_with_all_flag():
    """--all should respect .enforcerignore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "keep.py").write_text("print('keep')\n")
        Path(tmpdir, "skip.py").write_text("print('skip')\n")
        Path(tmpdir, ".enforcerignore").write_text("skip.py\n")

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--all",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert "keep.py" in result.output
        assert "skip.py" not in result.output


def test_no_enforcerignore_checks_all():
    """Without .enforcerignore, all files should be checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "a.py").write_text("print('a')\n")
        Path(tmpdir, "b.py").write_text("print('b')\n")

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "a.py", "--paths", "b.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert "a.py" in result.output
        assert "b.py" in result.output
