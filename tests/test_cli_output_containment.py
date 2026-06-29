"""--output path must be contained within workspace."""
from click.testing import CliRunner
from enforcer.cli import cli

_EMPTY_CONFIG = '''
from enforcer import Rule, Severity
RULES = []
WORKSPACE = "."
'''


def _write_config(workspace):
    import os
    cfg_path = os.path.join(workspace, "enforcer_config.py")
    with open(cfg_path, "w") as f:
        f.write(_EMPTY_CONFIG.replace('WORKSPACE = "."', f'WORKSPACE = {workspace!r}'))
    return cfg_path


def test_check_output_escape_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = _write_config(str(ws))
    escape = tmp_path / "escape.txt"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "check", "--paths", "x.py", "--config", cfg,
        "--workspace", str(ws), "--output", str(escape),
    ])
    assert result.exit_code == 2
    assert not escape.exists(), "escape file must not be written outside workspace"


def test_docs_output_escape_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = _write_config(str(ws))
    escape = tmp_path / "escape_docs.md"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "docs", "--config", cfg, "--output", str(escape),
    ])
    assert result.exit_code == 2
    assert not escape.exists(), "escape file must not be written outside workspace"


def test_check_output_inside_workspace_ok(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = _write_config(str(ws))
    outfile = ws / "results.txt"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "check", "--paths", "x.py", "--config", cfg,
        "--workspace", str(ws), "--output", str(outfile),
    ])
    assert result.exit_code == 0
    assert outfile.exists()
