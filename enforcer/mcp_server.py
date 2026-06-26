from __future__ import annotations
import json
import sys
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter

def check_conventions(paths: list[str] | None = None, format: str = "json") -> str:
    """Run convention checks. Returns formatted output."""
    config = load_config("enforcer_config.py")
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
            import os
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                ctx = builder.build(target.replace("**/", ""))
                shared_ctx[os.path.basename(target_path)] = ctx

    all_matches = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    reporter = Reporter(format=format)
    return reporter.render(all_matches)

def run_mcp_server():
    """Minimal stdio JSON-RPC server for MCP protocol."""
    for line in sys.stdin:
        try:
            msg = json.loads(line)
            if msg.get("method") == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "tools": [{
                            "name": "check_conventions",
                            "description": "Check files for convention violations",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "paths": {"type": "array", "items": {"type": "string"}},
                                    "format": {"type": "string", "enum": ["json", "text"]},
                                },
                            },
                        }]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif msg.get("method") == "tools/call":
                params = msg.get("params", {})
                args = params.get("arguments", {})
                result = check_conventions(
                    paths=args.get("paths"),
                    format=args.get("format", "json"),
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {"content": [{"type": "text", "text": result}]}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if "msg" in dir() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    run_mcp_server()
