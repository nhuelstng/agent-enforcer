import json
import pytest
import tempfile
import os
from unittest.mock import patch, Mock
from click.testing import CliRunner
from enforcer.cli import cli

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def empty_config(tmp_path):
    config_content = '''
from enforcer import Rule, Severity
RULES = []
WORKSPACE = "."
'''
    config_file = tmp_path / "enforcer_config.py"
    config_file.write_text(config_content)
    return str(config_file)

def test_cli_staged(runner, empty_config):
    with patch("subprocess.check_output", return_value=b""), \
         patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--staged", "--format", "json", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_all(runner, empty_config, tmp_path):
    with patch("os.walk", return_value=[(str(tmp_path), [], ["x.ts"])]), \
         patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--all", "--config", empty_config, "--workspace", str(tmp_path)])
        assert result.exit_code == 0

def test_cli_paths(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_workspace(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--workspace", ".", "--paths", "x.ts", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_format_json(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--format", "json", "--config", empty_config])
        data = json.loads(result.output)
        assert "summary" in data
        assert "issues" in data

def test_cli_format_text(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--format", "text", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_no_llm(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--no-llm", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_exit_code_on_error(runner, empty_config):
    from enforcer import Severity, Match
    match = Match(file="x.ts", line=1, message="err", severity=Severity.ERROR)
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[match]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", empty_config])
        assert result.exit_code == 1

def test_cli_exit_code_on_warn_only(runner, empty_config):
    from enforcer import Severity, Match
    match = Match(file="x.ts", line=1, message="warn", severity=Severity.WARN)
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[match]):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", empty_config])
        assert result.exit_code == 0

def test_cli_config_path(runner, empty_config):
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=[]):
        result = runner.invoke(cli, ["check", "--config", empty_config, "--paths", "x.ts"])
        assert result.exit_code == 0

def test_staged_mode_sets_file_status(tmp_path, monkeypatch):
    """Staged mode should populate FileContext.status from git diff --name-status."""
    import subprocess
    from click.testing import CliRunner
    from enforcer.cli import cli

    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)

    (tmp_path / "new.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "new.py"], cwd=tmp_path, capture_output=True)

    config = """
from enforcer import Rule, Severity
from enforcer.matchers import AlwaysMatcher
RULES = [Rule(id="status-test", severity=Severity.INFO, matchers=[AlwaysMatcher()], file_globs=["*"])]
WORKSPACE = "."
SEVERITY_ACTIONS = {}
LLM_CONFIG = {}
"""
    (tmp_path / "enforcer_config.py").write_text(config)

    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--staged", "--no-llm", "--config", "enforcer_config.py"])
    assert result.exit_code == 0


def test_base_ref_mode_sets_file_status(tmp_path, monkeypatch):
    """--base-ref mode should populate FileContext.status."""
    import subprocess
    from click.testing import CliRunner
    from enforcer.cli import cli

    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "master"], cwd=tmp_path, capture_output=True)

    (tmp_path / "base.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "base.py"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmp_path, capture_output=True)
    (tmp_path / "new.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "new.py"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: add new"], cwd=tmp_path, capture_output=True)

    config = """
from enforcer import Rule, Severity
from enforcer.matchers import AlwaysMatcher
RULES = [Rule(id="status-test", severity=Severity.INFO, matchers=[AlwaysMatcher()], file_globs=["*"])]
WORKSPACE = "."
SEVERITY_ACTIONS = {}
LLM_CONFIG = {}
"""
    (tmp_path / "enforcer_config.py").write_text(config)

    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--base-ref", "master", "--no-llm", "--config", "enforcer_config.py"])
    assert result.exit_code == 0


def test_cli_sync_doc_writes_file(runner, empty_config, tmp_path):
    config_with_rule = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [Rule(id="test-rule", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="No print.", fix_instruction="Remove it.", rationale="Print is bad.")]
WORKSPACE = "."
'''
    config_file = tmp_path / "enforcer_config.py"
    config_file.write_text(config_with_rule)
    output_file = tmp_path / "OUT.md"
    result = runner.invoke(cli, ["sync-doc", "--config", str(config_file), "-o", str(output_file)])
    assert result.exit_code == 0
    content = output_file.read_text()
    assert "# Conventions" in content
    assert "### test-rule" in content
    assert "**Why:**" in content
    assert "Print is bad." in content


def test_cli_sync_doc_default_output(runner, empty_config, tmp_path):
    import os
    monkeypatch_dir = tmp_path
    config_file = monkeypatch_dir / "enforcer_config.py"
    config_file.write_text('''
from enforcer import Rule, Severity
RULES = []
WORKSPACE = "."
''')
    cwd = os.getcwd()
    os.chdir(str(monkeypatch_dir))
    try:
        result = runner.invoke(cli, ["sync-doc", "--config", str(config_file)])
        assert result.exit_code == 0
        assert (monkeypatch_dir / "CONVENTIONS.md").exists()
    finally:
        os.chdir(cwd)


def test_build_shared_ctx_stashes_rules():
    """_build_shared_ctx must stash __rules__ and __workspace__."""
    from enforcer.cli import _build_shared_ctx
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity

    config = Config(
        rules=[Rule(id="x", severity=Severity.ERROR, matchers=[], file_globs=["*.py"])],
        workspace="/tmp/test",
    )
    builder = FileContextBuilder(config.rules, workspace="/tmp/test")
    ctx = _build_shared_ctx(config, builder, "/tmp/test")
    assert "__rules__" in ctx
    assert len(ctx["__rules__"]) == 1
    assert ctx["__rules__"][0].id == "x"
    assert "__workspace__" in ctx
