import json
from unittest.mock import patch, MagicMock
from enforcer.mcp_server import check_conventions, list_conventions, verify_fix, run_mcp_server


def test_list_conventions_returns_markdown():
    md = list_conventions()
    assert "# Conventions" in md


def test_verify_fix_returns_pass_or_fail():
    result = json.loads(verify_fix(path="README.md", rule_id="max-lines-readme"))
    assert "summary" in result
    assert "issues" in result


def test_verify_fix_unknown_rule():
    result = json.loads(verify_fix(path="x.ts", rule_id="nonexistent"))
    assert result["summary"]["total"] == 0


def test_check_conventions_with_paths():
    result = json.loads(check_conventions(paths=["README.md"]))
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
    assert "Unknown tool" in resp["result"]["content"][0]["text"]


def test_run_mcp_server_invalid_json():
    import io
    req = 'not json at all\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] is None
    assert resp["error"]["code"] == -32603
