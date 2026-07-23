import json
from unittest.mock import patch, MagicMock
from enforcer.mcp_server import check_conventions, list_conventions, verify_fix, run_mcp_server
from enforcer.types import LLMConfig


def test_list_conventions_returns_markdown():
    md = list_conventions()
    assert "# Conventions" in md


def test_verify_fix_returns_pass_or_fail():
    result = json.loads(verify_fix(path="README.md", rule_id="readme-max-lines", no_llm=True))
    assert "summary" in result
    assert "issues" in result


def test_verify_fix_diff_only_rule_fires():
    import os
    f = "enforcer/_test_vf.py"
    with open(f, "w") as fh:
        fh.write('print("hello")\n')
    try:
        result = json.loads(verify_fix(path=f, rule_id="no-print", no_llm=True))
        assert result["summary"]["total"] > 0
    finally:
        os.unlink(f)


def test_verify_fix_unknown_rule():
    result = json.loads(verify_fix(path="x.ts", rule_id="nonexistent"))
    assert result["summary"]["total"] == 0


def test_check_conventions_with_paths():
    result = json.loads(check_conventions(paths=["README.md"], no_llm=True))
    assert "summary" in result


def test_run_mcp_server_tools_list():
    import io
    import sys
    req = '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] == 1
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "check_conventions" in tool_names
    assert "list_conventions" in tool_names
    assert "verify_fix" in tool_names


def test_run_mcp_server_check_conventions_call():
    import io
    req = '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_conventions", "arguments": {}}}\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] == 2
    assert "# Conventions" in resp["result"]["content"][0]["text"]


def test_run_mcp_server_unknown_tool():
    import io
    req = '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "bogus", "arguments": {}}}\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] == 3
    assert resp["error"]["code"] == -32601
    assert "bogus" in resp["error"]["message"]


def test_run_mcp_server_invalid_json():
    import io
    req = 'not json at all\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] is None
    assert resp["error"]["code"] == -32603


def test_run_mcp_server_error_no_leak():
    """Exception details must not leak to client — generic message only."""
    import io
    leak_marker = "SECRET_INTERNAL_PATH_xyz"
    with patch("enforcer.mcp_server._handle_tool_call",
               side_effect=ValueError(leak_marker)):
        req = '{"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "check_conventions", "arguments": {}}}\n'
        with patch("sys.stdin", io.StringIO(req)):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] == 9
    assert resp["error"]["code"] == -32603
    assert leak_marker not in resp["error"]["message"]
    assert "Traceback" not in resp["error"]["message"]


def test_check_conventions_empty_paths_not_staged():
    """paths=[] must NOT trigger staged mode (which calls git diff)."""
    call_log: list = []

    def fake_collect_files(staged, all_files, paths, ws, base_ref=None):
        call_log.append({"staged": staged, "paths": paths})
        return [], {}

    with patch("enforcer.mcp_server._collect_files", side_effect=fake_collect_files), \
         patch("enforcer.mcp_server._run_check_pass", return_value=[]), \
         patch("enforcer.mcp_server.RuleRunner"):
        check_conventions(paths=[])
    assert call_log, "collect_files must be called"
    assert call_log[0]["staged"] is False, "paths=[] must not imply staged=True"


def test_verify_fix_respects_file_globs():
    """verify_fix on a rule with file_globs=['**/*.ts'] must return 0 matches for a .py file."""
    from enforcer import Severity
    from enforcer.rule import Rule
    from enforcer.matchers import RegexMatcher
    ts_rule = Rule(
        id="ts-only-regex-test",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"console\.log")],
        file_globs=["**/*.ts"],
        message="ts only",
    )
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        py_file = os.path.join(tmp, "x.py")
        with open(py_file, "w") as f:
            f.write("console.log('leak')\n")
        config = MagicMock()
        config.workspace = tmp
        config.rules = [ts_rule]
        config.llm_config = LLMConfig(concurrency=1, timeout=5)
        config.severity_actions = {}
        with patch("enforcer.mcp_server.load_config", return_value=config):
            result = json.loads(verify_fix(path="x.py", rule_id="ts-only-regex-test"))
    assert result["summary"]["total"] == 0


class TestMcpExplainRule:
    """the explain_rule MCP tool returns structured rule explainer."""

    def test_explain_rule_returns_json(self, tmp_path, monkeypatch):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        monkeypatch.setenv("ENFORCER_CONFIG", str(cfg))
        from enforcer.mcp_server import explain_rule
        result = explain_rule("no-print")
        import json
        data = json.loads(result)
        assert data["rule_id"] == "no-print"
        assert data["severity"] == "error"

    def test_explain_rule_unknown_returns_error(self, tmp_path, monkeypatch):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        monkeypatch.setenv("ENFORCER_CONFIG", str(cfg))
        from enforcer.mcp_server import explain_rule
        result = explain_rule("nonexistent")
        import json
        data = json.loads(result)
        assert "error" in data or "not found" in result.lower()

    def test_explain_rule_in_tool_definitions(self):
        from enforcer.mcp_server import _tool_definitions
        tools = _tool_definitions()
        names = [t["name"] for t in tools]
        assert "explain_rule" in names
