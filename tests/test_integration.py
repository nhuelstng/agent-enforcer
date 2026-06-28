"""Integration tests for cross-feature combinations identified as gaps."""
import tempfile
from pathlib import Path
from click.testing import CliRunner
from enforcer.cli import cli


def test_duplicate_detection_via_cli():
    """DuplicateCodeMatcher should work end-to-end through CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code = "def process(data):\n    result = []\n    for item in data:\n        result.append(item * 2)\n    return result\n"
        Path(tmpdir, "a.py").write_text(code)
        Path(tmpdir, "b.py").write_text(code)

        config = '''
from enforcer import Rule, Severity
from enforcer.matchers import DuplicateCodeMatcher
RULES = [
    Rule(id="no-dup", severity=Severity.WARN,
         matchers=[DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)],
         file_globs=["*.py"], message="Duplicate: {matched_value}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "a.py", "--paths", "b.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        assert "Duplicate" in result.output or "duplicate" in result.output.lower()


def test_enforcerignore_not_applied_to_staged():
    """--staged should NOT apply .enforcerignore (user explicitly staged the file)."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)

        Path(tmpdir, "keep.py").write_text("print('keep')\n")
        Path(tmpdir, "skip.py").write_text("print('skip')\n")
        Path(tmpdir, ".enforcerignore").write_text("skip.py\n")

        subprocess.run(["git", "add", "keep.py", "skip.py"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, "keep.py").write_text("print('modified')\n")
        Path(tmpdir, "skip.py").write_text("print('modified')\n")
        subprocess.run(["git", "add", "keep.py", "skip.py"], cwd=tmpdir, capture_output=True)

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
        result = runner.invoke(cli, ["check", "--staged",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm"])
        # Both files should be checked — .enforcerignore skipped for --staged
        assert "keep.py" in result.output
        assert "skip.py" in result.output


def test_fix_with_metadata_rules():
    """--fix should not crash when metadata rules produce matches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test.py").write_text("print('x')\n")
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, ".git/COMMIT_EDITMSG").write_text("bad message")

        config = '''
from enforcer import Rule, Severity, RuleType
from enforcer.matchers import RegexMatcher, CommitMessageMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")], file_globs=["*.py"],
         message="print() at {file}:{line}",
         fix=lambda ctx, m: (ctx.raw or "").replace("print(", "logger.debug(")),
    Rule(id="commit-msg", severity=Severity.WARN,
         matchers=[CommitMessageMatcher(pattern=r"^(feat|fix):\\s+.+")],
         file_globs=["*"], rule_type=RuleType.METADATA,
         message="Bad commit message: {matched_value}"),
]
WORKSPACE = "."
'''
        Path(tmpdir, "enforcer_config.py").write_text(config)
        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "test.py",
                                      "--config", f"{tmpdir}/enforcer_config.py",
                                      "--workspace", tmpdir, "--no-llm", "--fix"])
        # Should not crash — fix applies to content rules, metadata match ignored
        assert result.exit_code in (0, 1)
        content = Path(tmpdir, "test.py").read_text()
        assert "logger.debug" in content


def test_duplicate_detection_finalize_idempotent():
    """Calling finalize_duplicates twice should not double matches."""
    from enforcer.matchers.duplicate_code import DuplicateCodeMatcher
    from enforcer.types import FileContext
    code = "def foo():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    matcher = DuplicateCodeMatcher(min_tokens=3, min_overlap=0.8)
    shared = {}
    matcher.find(FileContext(path="a.py", raw=code), shared)
    matcher.find(FileContext(path="b.py", raw=code), shared)
    first = matcher.finalize_duplicates(shared)
    second = matcher.finalize_duplicates(shared)
    assert len(first) == 2
    assert len(second) == 0  # finalized flag prevents re-run


def test_duplicate_detection_two_instances_no_collision():
    """Two DuplicateCodeMatcher instances with different configs should not collide."""
    from enforcer.matchers.duplicate_code import DuplicateCodeMatcher
    from enforcer.types import FileContext
    code = "def foo():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    matcher_a = DuplicateCodeMatcher(min_tokens=3, min_overlap=0.8)
    matcher_b = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.5)
    shared = {}
    matcher_a.find(FileContext(path="a.py", raw=code), shared)
    matcher_a.find(FileContext(path="b.py", raw=code), shared)
    matcher_b.find(FileContext(path="a.py", raw=code), shared)
    matcher_b.find(FileContext(path="b.py", raw=code), shared)
    matches_a = matcher_a.finalize_duplicates(shared)
    matches_b = matcher_b.finalize_duplicates(shared)
    # Both should work independently — no key collision
    assert len(matches_a) == 2
    # matcher_b with min_tokens=5 finds fewer grams, may or may not match
    # but should NOT crash or return matches from matcher_a's index


import subprocess  # ponytail: needed by test_enforcerignore_not_applied_to_staged
