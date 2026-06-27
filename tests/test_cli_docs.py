import os
from click.testing import CliRunner
from enforcer.cli import cli


_CONFIG = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

WORKSPACE = "."

RULES = [
    Rule(
        id="no-raw-hex",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\\b")],
        file_globs=["**/*.ts"],
        message="Raw hex color '{matched_value}' found.",
        fix_instruction="Use var(--color-*).",
    ),
    Rule(
        id="max-lines-readme",
        severity=Severity.WARN,
        matchers=[],
        file_globs=["README.md"],
        message="README too long.",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "print",
    Severity.INFO: "hint",
}
'''


def _write_config(tmp_path):
    cfg = tmp_path / "enforcer_config.py"
    cfg.write_text(_CONFIG)
    return str(cfg)


def test_docs_to_stdout(tmp_path):
    cfg = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["docs", "--config", cfg])
    assert result.exit_code == 0
    assert "no-raw-hex" in result.output
    assert "max-lines-readme" in result.output
    assert "# Conventions" in result.output


def test_docs_to_file(tmp_path):
    cfg = _write_config(tmp_path)
    out_file = tmp_path / "RULES.md"
    runner = CliRunner()
    result = runner.invoke(cli, ["docs", "--config", cfg, "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text()
    assert "## no-raw-hex" in content
    assert "## max-lines-readme" in content
    assert "ERROR" in content
