import os
from unittest.mock import patch
from click.testing import CliRunner
from enforcer.cli import cli


_WARN_CONFIG = '''
from enforcer import Rule, Severity
from enforcer.matchers import AlwaysMatcher

WORKSPACE = "."

RULES = [
    Rule(
        id="warn-rule",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="warn-trigger")],
        file_globs=["**/*.ts"],
        message="Warn triggered.",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
'''

_ERROR_CONFIG = '''
from enforcer import Rule, Severity
from enforcer.matchers import AlwaysMatcher

WORKSPACE = "."

RULES = [
    Rule(
        id="error-rule",
        severity=Severity.ERROR,
        matchers=[AlwaysMatcher(matched_value="error-trigger")],
        file_globs=["**/*.ts"],
        message="Error triggered.",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
'''


def _write_config(tmp_path, content):
    cfg = tmp_path / "enforcer_config.py"
    cfg.write_text(content)
    return str(cfg)


def _real_match(file="x.ts"):
    from enforcer import Match, Severity
    return [Match(file=file, line=1, rule_id="warn-rule", severity=Severity.WARN, message="Warn triggered.")]


def _real_error_match(file="x.ts"):
    from enforcer import Match, Severity
    return [Match(file=file, line=1, rule_id="error-rule", severity=Severity.ERROR, message="Error triggered.")]


def test_warn_blocks_commit_without_confirm(tmp_path):
    cfg = _write_config(tmp_path, _WARN_CONFIG)
    runner = CliRunner()
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=_real_match()):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", cfg])
        assert result.exit_code == 1


def test_warn_allows_commit_with_confirm(tmp_path):
    cfg = _write_config(tmp_path, _WARN_CONFIG)
    runner = CliRunner()
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=_real_match()):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", cfg, "--confirm-read-warnings"])
        assert result.exit_code == 0


def test_error_blocks_even_with_confirm(tmp_path):
    cfg = _write_config(tmp_path, _ERROR_CONFIG)
    runner = CliRunner()
    with patch("enforcer.runner.RuleRunner.run_rules_for_file", return_value=_real_error_match()):
        result = runner.invoke(cli, ["check", "--paths", "x.ts", "--config", cfg, "--confirm-read-warnings"])
        assert result.exit_code == 1
