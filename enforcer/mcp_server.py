"""MCP server: JSON-RPC over stdio. Tools: check_conventions, list_conventions, verify_fix."""
from __future__ import annotations
import json
import os
import sys
from enforcer.config import load_config
from enforcer.reporter import Reporter
from enforcer.check_service import run_check, verify_fix_matches, CheckRequest


def _config_path() -> str:
    return os.environ.get("ENFORCER_CONFIG", "enforcer_config")

def check_conventions(paths: list[str] | None = None, format: str = "json", no_llm: bool = False) -> str:
    """Run convention checks. Returns formatted output."""
    config = load_config(_config_path())
    all_matches = run_check(config, CheckRequest(
        staged=paths is None, paths=tuple(paths) if paths else (), no_llm=no_llm,
    ))
    reporter = Reporter(format=format)
    return reporter.render(all_matches, severity_actions=config.severity_actions)

def list_conventions() -> str:
    """Return all configured rules as markdown documentation."""
    from enforcer.docs import render_rules_markdown
    config = load_config(_config_path())
    return render_rules_markdown(config.rules)

def verify_fix(path: str, rule_id: str, format: str = "json", no_llm: bool = False) -> str:
    """Re-check a single rule on a single file. Returns formatted output."""
    config = load_config(_config_path())
    matches = verify_fix_matches(config, path, rule_id, no_llm=no_llm)
    reporter = Reporter(format=format)
    # An unknown rule id (None) formats identically to a clean file: an empty result.
    return reporter.render(matches or [], severity_actions=config.severity_actions)

def explain_rule(rule_id: str) -> str:
    """Explain a rule: what it matches, what it ignores, worked example. Returns JSON."""
    import json
    from enforcer.explain import load_rule_for_explain, render_rule_explainer_json
    result = load_rule_for_explain(_config_path(), rule_id)
    if result.rule is None:
        return json.dumps({"error": f"No rule with id '{rule_id}'", "suggestions": result.suggestions})
    return json.dumps(render_rule_explainer_json(result.rule, workspace=result.config_workspace), indent=2)

def _tool_definitions() -> list[dict]:
    """Return MCP tool definitions for tools/list response."""
    return [
        {
            "name": "check_conventions",
            "description": "Check files for convention violations",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
            },
        },
        {
            "name": "list_conventions",
            "description": "List all configured convention rules as documentation",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "verify_fix",
            "description": "Re-check a single rule on a single file after a fix",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "rule_id": {"type": "string"},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
                "required": ["path", "rule_id"],
            },
        },
        {
            "name": "explain_rule",
            "description": "Explain what a rule matches, what it ignores, and show a worked example",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                },
                "required": ["rule_id"],
            },
        },
    ]


def _send_response(msg_id, result) -> None:
    """Write a JSON-RPC success response to stdout."""
    response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _send_error(msg_id, code: int, message: str) -> None:
    """Write a JSON-RPC error response to stdout."""
    response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _handle_tool_call(params: dict, msg_id) -> str | None:
    """Dispatch a tools/call request to the appropriate function. Returns result string, or None if error sent."""
    tool_name = params.get("name")
    args = params.get("arguments", {})
    if tool_name == "check_conventions":
        return check_conventions(paths=args.get("paths"), format=args.get("format", "json"))
    if tool_name == "list_conventions":
        return list_conventions()
    if tool_name == "verify_fix":
        return verify_fix(path=args.get("path"), rule_id=args.get("rule_id"), format=args.get("format", "json"))
    if tool_name == "explain_rule":
        return explain_rule(rule_id=args.get("rule_id"))
    _send_error(msg_id, -32601, f"Unknown tool: {tool_name}")
    return None


def _dispatch_method(msg: dict) -> None:
    """Dispatch a single MCP method call. Sends response or error."""
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        _send_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "enforcer", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        })
    elif method == "tools/list":
        _send_response(msg_id, {"tools": _tool_definitions()})
    elif method == "tools/call":
        result = _handle_tool_call(msg.get("params", {}), msg_id)
        if result is not None:
            _send_response(msg_id, {"content": [{"type": "text", "text": result}]})
    elif method == "notifications/initialized":
        pass
    else:
        _send_error(msg_id, -32601, f"Method not found: {method}")


def _handle_mcp_error(msg, e):
    """Log MCP error and send error response."""
    sys.stderr.write(f"[enforcer] MCP error: {e}\n")
    _send_error(msg.get("id") if msg else None, -32603, "Internal error")


def _process_mcp_line(line: str) -> dict | None:
    """Parse and dispatch a single MCP line. Returns the msg or None."""
    msg = None
    try:
        msg = json.loads(line)
        _dispatch_method(msg)
    except Exception as e:
        _handle_mcp_error(msg, e)
    return msg


def run_mcp_server():
    """Minimal stdio JSON-RPC server for MCP protocol."""
    for line in sys.stdin:
        _process_mcp_line(line)

if __name__ == "__main__":
    run_mcp_server()
