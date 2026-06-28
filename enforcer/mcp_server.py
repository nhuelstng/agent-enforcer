"""MCP server: JSON-RPC over stdio. Tools: check_conventions, list_conventions, verify_fix."""
from __future__ import annotations
import json
import os
import sys
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter


def _config_path() -> str:
    return os.environ.get("ENFORCER_CONFIG", "enforcer_config.py")

def check_conventions(paths: list[str] | None = None, format: str = "json") -> str:
    """Run convention checks. Returns formatted output."""
    config = load_config(_config_path())
    ws = config.workspace

    if not paths:
        import subprocess
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            stderr=subprocess.DEVNULL,
        )
        file_list = result.decode().strip().split("\n") if result.strip() else []
    else:
        file_list = paths

    runner = RuleRunner(config.rules, workspace=ws, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                ctx = builder.build(target.replace("**/", ""))
                shared_ctx[target] = ctx

    all_matches = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    reporter = Reporter(format=format)
    return reporter.render(all_matches)

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

    runner = RuleRunner(config.rules, workspace=ws, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for target in getattr(rule, "read_targets", []):
        target_path = os.path.join(ws, target.replace("**/", ""))
        if os.path.exists(target_path):
            ctx = builder.build(target.replace("**/", ""))
            shared_ctx[target] = ctx

    ctx = builder.build(path)
    matches = rule.check(ctx, shared_ctx)
    if matches and rule.llm_consequence:
        matches = runner.llm_executor.execute(matches, rule.llm_consequence, ctx, shared_ctx)

    reporter = Reporter(format=format)
    return reporter.render(matches)

def run_mcp_server():
    """Minimal stdio JSON-RPC server for MCP protocol."""
    for line in sys.stdin:
        msg = None
        try:
            msg = json.loads(line)
            method = msg.get("method")
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "enforcer", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "tools": [
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
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif msg.get("method") == "tools/call":
                params = msg.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})
                if tool_name == "check_conventions":
                    result = check_conventions(
                        paths=args.get("paths"),
                        format=args.get("format", "json"),
                    )
                elif tool_name == "list_conventions":
                    result = list_conventions()
                elif tool_name == "verify_fix":
                    result = verify_fix(
                        path=args.get("path"),
                        rule_id=args.get("rule_id"),
                        format=args.get("format", "json"),
                    )
                else:
                    result = json.dumps({"error": f"Unknown tool: {tool_name}"})
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {"content": [{"type": "text", "text": result}]}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif method == "notifications/initialized":
                pass
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if msg else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
