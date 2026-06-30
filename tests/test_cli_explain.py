"""Tests for `enforcer explain` CLI command."""
import pytest
from click.testing import CliRunner
from enforcer.cli import cli


_CONFIG = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

WORKSPACE = "."

RULES = [
    Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\\s*print\\s*\\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found.",
        fix_instruction="Replace print().",
        rationale="print() pollutes stdout.",
    ),
    Rule(
        id="max-lines",
        severity=Severity.WARN,
        matchers=[],
        file_globs=["README.md"],
        message="README too long.",
    ),
]
'''


def _write_config(tmp_path):
    cfg = tmp_path / "enforcer_config.py"
    cfg.write_text(_CONFIG)
    return str(cfg)


class TestCliExplainFound:
    """renders an explainer for a valid rule id."""

    @pytest.mark.parametrize("rule_id", ["no-print", "max-lines"])
    def test_explains_existing_rule(self, rule_id, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", rule_id, "--config", cfg])
        assert result.exit_code == 0
        assert f"Rule: {rule_id}" in result.output

    def test_includes_matcher_detail(self, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", "no-print", "--config", cfg])
        assert "RegexMatcher" in result.output
        assert "What:" in result.output


class TestCliExplainClean:
    """handles unknown rule ids gracefully."""

    @pytest.mark.parametrize("bad_id", ["nonexistent", "totally-fake"])
    def test_unknown_rule_suggests(self, bad_id, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", bad_id, "--config", cfg])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no rule" in result.output.lower()

    def test_json_format(self, tmp_path):
        cfg = _write_config(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", "no-print", "--config", cfg, "--format", "json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["rule_id"] == "no-print"
