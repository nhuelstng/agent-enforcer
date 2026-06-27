"""Tests for CLI --fix flag."""
import tempfile
from pathlib import Path
from click.testing import CliRunner
from enforcer.cli import cli

def test_fix_flag_applies_fixes():
    """--fix should apply fix functions and modify files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('hello')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm", "--fix"])
        content = Path(tmpdir, "test.py").read_text()
        assert "logger.debug" in content
        assert "print(" not in content

def test_fix_flag_reports_applied():
    """--fix should report which fixes were applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('x')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm", "--fix"])
        assert "1 fix" in result.output or "fixed" in result.output.lower()

def test_no_fix_flag_does_not_modify():
    """Without --fix, files should not be modified."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('hello')\n")
        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        content = Path(tmpdir, "test.py").read_text()
        assert "print('hello')" in content
