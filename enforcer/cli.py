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

@cli.command()
@click.option("--staged", is_flag=True, help="Check staged files only")
@click.option("--all", "all_files", is_flag=True, help="Check entire repo")
@click.option("--paths", multiple=True, help="Check specific files")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]))
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
        file_list = []
        for root, dirs, files in os.walk(ws):
            if ".git" in dirs:
                dirs.remove(".git")
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
                shared_ctx[os.path.basename(target_path)] = target_ctx

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

if __name__ == "__main__":
    cli()
