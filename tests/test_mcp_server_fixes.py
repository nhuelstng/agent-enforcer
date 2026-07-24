"""Issue 2: MCP staged mode must not load enforcerignore. Issue 3: unknown tool returns JSON-RPC error -32601."""
import io
import json
from unittest.mock import patch
from enforcer.mcp_server import check_conventions, run_mcp_server


def test_mcp_staged_mode_skips_enforcerignore():
    """check_conventions(paths=None) is staged mode — must NOT call load_enforcerignore."""
    with patch("enforcer.check_service.collect_files", return_value=([], {})), \
         patch("enforcer.check_service.run_check_pass", return_value=[]), \
         patch("enforcer.check_service.load_enforcerignore") as mock_load, \
         patch("enforcer.check_service.RuleRunner"):
        check_conventions(paths=None)
    mock_load.assert_not_called(), "staged mode must skip load_enforcerignore"


def test_mcp_unknown_tool_returns_method_not_found_error():
    """Unknown tool name must produce JSON-RPC error with code -32601, not a success result."""
    req = '{"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "bogus_tool", "arguments": {}}}\n'
    with patch("sys.stdin", io.StringIO(req)):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            run_mcp_server()
    resp = json.loads(mock_out.getvalue().strip())
    assert resp["id"] == 7
    assert "error" in resp, "unknown tool must produce error response, not success result"
    assert resp["error"]["code"] == -32601, "must use -32601 (Method not found)"
    assert "result" not in resp
