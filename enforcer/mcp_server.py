"""MCP server: JSON-RPC over stdio. Tools: check_conventions, list_conventions, verify_fix."""
from __future__ import annotations
import json
import os
import sys
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter
from enforcer.cli import _collect_files, _build_shared_ctx, _run_checks, _build_change_context
from enforcer.ignore import load_enforcerignore, is_ignored


def _config_path() -> str:
    return os.environ.get("ENFORCER_CONFIG", "enforcer_config.py")

def check_conventions(paths: list[str] | None = None, format: str = "json") -> str:
    """Run convention checks. Returns formatted output."""
    config = load_config(_config_path())
    ws = config.workspace

    file_list, status_map = _collect_files(
        staged=paths is None,
        all_files=False,
        paths=tuple(paths) if paths else (),
        ws=ws,
    )

    ignore_patterns = load_enforcerignore(ws) if paths is not None else []
    if ignore_patterns:
        file_list = [f for f in file_list if not is_ignored(f, ignore_patterns)]

    runner = RuleRunner(config.rules, workspace=ws, no_llm=False, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)
    shared_ctx = _build_shared_ctx(config, builder, ws)

    change_ctx = _build_change_context(ws, status_map)
    shared_ctx["__change__"] = change_ctx

    all_matches = _run_checks(
        runner, builder, file_list, shared_ctx, ws,
        staged=paths is None, diff_ref=None, status_map=status_map,
    )

    all_matches.extend(runner.run_metadata_rules(shared_ctx))
    all_matches.extend(runner.run_cross_file_finalizers(shared_ctx))

    reporter = Reporter(format=format)
    return reporter.render(all_matches, severity_actions=config.severity_actions)

def list_conventions() -> str:
    """Return all configured rules as markdown documentation."""
    from enforcer.docs import render_rules_markdown
    config = load_config(_config_path())
    return render_rules_markdown(config.rules)

def verify_fix(path: str, rule_id: str, format: str = "json") -> str:
    """Re-check a single rule on a single file. Returns formatted output."""
    config = load_config(_config_path())
    ws = config.workspace

    rule = next((r for r in config.rules if r.id == rule_id), None)
    if not rule:
        return json.dumps({"summary": {"total": 0, "errors": 0, "warnings": 0, "info": 0}, "issues": []})

    runner = RuleRunner(config.rules, workspace=ws, no_llm=False, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)
    shared_ctx = _build_shared_ctx(config, builder, ws)

    # ponytail: honor file_globs/exclude_globs before check() — mirrors RuleRunner._file_matches
    if not runner._file_matches(path, rule):
        reporter = Reporter(format=format)
        return reporter.render([], severity_actions=config.severity_actions)

    ctx = builder.build(path)
    # ponytail: verify_fix re-checks full file post-fix; set all lines as changed so diff_only rules fire
    if ctx.raw is not None:
        ctx.changed_lines = set(range(1, ctx.raw.count("\n") + 2))
    matches = rule.check(ctx, shared_ctx)
    if matches and rule.llm_consequence:
        matches = runner.llm_executor.execute(matches, rule.llm_consequence, ctx, shared_ctx)

    reporter = Reporter(format=format)
    return reporter.render(matches, severity_actions=config.severity_actions)

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
    _send_error(msg_id, -32601, f"Unknown tool: {tool_name}")
    return None


def run_mcp_server():
    """Minimal stdio JSON-RPC server for MCP protocol."""
    for line in sys.stdin:
        msg = None
        try:
            msg = json.loads(line)
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
        except Exception as e:
            sys.stderr.write(f"[enforcer] MCP error: {e}\n")
            _send_error(msg.get("id") if msg else None, -32603, "Internal error")

if __name__ == "__main__":
    run_mcp_server()
