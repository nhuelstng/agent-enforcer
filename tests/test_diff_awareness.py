"""Tests for diff-awareness: FileContext carries changed_lines from git diff."""
import tempfile
from pathlib import Path
from click.testing import CliRunner
from enforcer.cli import cli
from enforcer.types import FileContext
from enforcer.context import FileContextBuilder

def test_file_context_has_changed_lines_field():
    """FileContext should have a changed_lines field defaulting to None."""
    ctx = FileContext(path="foo.py")
    assert ctx.changed_lines is None

def test_file_context_changed_lines_set():
    """FileContext should accept changed_lines as a set of ints."""
    ctx = FileContext(path="foo.py", changed_lines={1, 2, 5})
    assert ctx.changed_lines == {1, 2, 5}

def test_cli_staged_passes_changed_lines():
    """When --staged is used, FileContext should have changed_lines populated from git diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("line1\nline2\nline3\nline4\nline5\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("line1\nMODIFIED2\nline3\nMODIFIED4\nline5\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="test", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"MODIFIED")], file_globs=["*.py"],
         diff_only=True, message="MODIFIED found at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--staged", "--config",
                                      f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert result.exit_code == 1, f"Expected 1 (violations on changed lines), got {result.exit_code}. Output: {result.output}"
        assert "MODIFIED" in result.output

def test_diff_only_rule_skips_unchanged_lines():
    """A rule with diff_only=True should not flag violations on unchanged lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("print('bad')\nline2\nline3\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("print('bad')\nline2\nCHANGED\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         diff_only=True, message="print() at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--staged", "--config",
                                      f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert result.exit_code == 0, f"Expected 0 (diff_only suppressed), got {result.exit_code}. Output: {result.output}"

def test_non_diff_only_rule_flags_all_lines():
    """A rule WITHOUT diff_only should flag violations on all lines, changed or not."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("print('bad')\nline2\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("print('bad')\nCHANGED\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)

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
        result = runner.invoke(cli, ["check", "--staged", "--config",
                                      f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert result.exit_code == 1, f"Expected 1 (no diff_only), got {result.exit_code}. Output: {result.output}"


def test_diff_only_pure_deletion_suppresses_all():
    """diff_only should suppress all line-level matches on pure-deletion (no added lines)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("print('bad')\nline2\nline3\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        # Pure deletion: remove line 1, no additions
        Path(tmpdir, "app.py").write_text("line2\nline3\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         diff_only=True, message="print() at {file}:{line}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--staged", "--config",
                                      f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        # print('bad') was deleted, not added. diff_only should suppress.
        assert result.exit_code == 0, f"Expected 0 (pure deletion, no added violations), got {result.exit_code}. Output: {result.output}"


def test_diff_only_file_level_matcher_passes_through():
    """File-level matchers (line==0) should pass through diff_only filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "app.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        # Add a line — file-level matcher should still fire (line==0 passes through)
        Path(tmpdir, "app.py").write_text("x = 1\ny = 2\n")
        subprocess.run(["git", "add", "app.py"], cwd=tmpdir, capture_output=True)

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import LineCountMatcher
RULES = [
    Rule(id="max-lines", severity=Severity.WARN,
         matchers=[LineCountMatcher(max_lines=1)], file_globs=["*.py"],
         diff_only=True, message="File has {matched_value} lines (max 1)"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--staged", "--config",
                                      f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        # LineCountMatcher emits line=0 (file-level). diff_only should let it through.
        assert "max-lines" in result.output, f"Expected file-level match to pass diff_only. Output: {result.output}"
