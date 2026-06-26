from __future__ import annotations
import os
import subprocess
import sys
import click
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter

@click.group()
def cli():
    """Convention enforcement tool for coding agents."""
    pass

def _glob_any_match(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)

@cli.command()
@click.option("--staged", is_flag=True, help="Check staged files only")
@click.option("--all", "all_files", is_flag=True, help="Check entire repo")
@click.option("--paths", multiple=True, help="Check specific files")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text", "sarif"]))
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--workspace", default=None, help="Global workspace root")
@click.option("--severity", default="info", type=click.Choice(["error", "warn", "info"]))
@click.option("--no-llm", is_flag=True, help="Skip LLM consequences")
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm):
    """Check files for convention violations."""
    from enforcer.types import Severity

    config = load_config(config_path)
    ws = workspace or config.workspace

    if staged:
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            stderr=subprocess.DEVNULL,
        )
        file_list = result.decode().strip().split("\n") if result.strip() else []
    elif all_files:
        _JUNK_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                       ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
                       "*.egg-info"}
        file_list = []
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if not _glob_any_match(d, _JUNK_DIRS)]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
    elif paths:
        file_list = list(paths)
    else:
        file_list = []

    sev_map = {"error": Severity.ERROR, "warn": Severity.WARN, "info": Severity.INFO}

    runner = RuleRunner(
        config.rules,
        workspace=ws,
        no_llm=no_llm,
        min_severity=sev_map[severity],
        llm_config=config.llm_config,
    )

    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                target_ctx = builder.build(target.replace("**/", ""))
                shared_ctx[target] = target_ctx

    all_matches = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    reporter = Reporter(format=fmt)
    output = reporter.render(all_matches)
    click.echo(output)
    sys.exit(reporter.exit_code(all_matches))

@cli.command()
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
def docs(config_path, output):
    """Generate markdown documentation of all configured rules."""
    from enforcer.docs import render_rules_markdown

    config = load_config(config_path)
    md = render_rules_markdown(config.rules)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        click.echo(f"Documentation written to {output}")
    else:
        click.echo(md)

if __name__ == "__main__":
    cli()
