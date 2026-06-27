"""Tests that read_targets with glob patterns actually glob the filesystem."""
import tempfile
from pathlib import Path
from enforcer.matchers.file_exists import FileExistsMatcher
from enforcer.types import FileContext


def test_file_exists_matcher_globs_wildcard():
    """FileExistsMatcher should find files matching a glob pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "test_artifacts.py").write_text("x = 1")
        Path(tmpdir, "test_admin.py").write_text("x = 1")

        matcher = FileExistsMatcher(
            read_target="test_*.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="app/api/artifacts.py", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1
        assert "exists" in matches[0].matched_value


def test_file_exists_matcher_recursive_glob():
    """FileExistsMatcher should handle ** recursive globs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "tests").mkdir()
        Path(tmpdir, "tests", "test_foo.py").write_text("x = 1")

        matcher = FileExistsMatcher(
            read_target="**/test_*.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="src/foo.ts", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1


def test_file_exists_matcher_no_match():
    """FileExistsMatcher returns empty when no files match glob."""
    with tempfile.TemporaryDirectory() as tmpdir:
        matcher = FileExistsMatcher(
            read_target="test_*.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="app/api/artifacts.py", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert matches == []


def test_cli_read_targets_globbed_into_shared_ctx():
    """CLI should glob read_targets and populate shared_ctx with matched files."""
    import tempfile
    from pathlib import Path
    from click.testing import CliRunner
    from enforcer.cli import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "tests", "integration").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "artifacts.py").write_text("x = 1")
        Path(tmpdir, "backend", "tests", "integration", "test_artifacts.py").write_text("x = 1")

        config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import FileExistsMatcher
from enforcer.combinators import Not

RULES = [
    Rule(
        id="test-exists",
        severity=Severity.WARN,
        matchers=[Not(FileExistsMatcher(read_target="backend/tests/integration/test_*.py"))],
        file_globs=["backend/app/api/*.py"],
        message="No test for {file}",
        fix_instruction="Create test.",
    ),
]
WORKSPACE = "."
'''
        config_path = Path(tmpdir, "enforcer_config.py")
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--paths", "backend/app/api/artifacts.py",
                                      "--config", str(config_path), "--no-llm",
                                      "--workspace", tmpdir])
        assert result.exit_code == 0, f"Expected 0, got {result.exit_code}. Output: {result.output}"
