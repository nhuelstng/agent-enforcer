"""Command-line interface: check, docs, install commands."""
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
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text", "sarif"]), help="Output format: text, json, or sarif")
@click.option("--config", "config_path", default="enforcer_config.py", help="Path to enforcer_config.py (default: enforcer_config.py)")
@click.option("--workspace", default=None, help="Global workspace root")
@click.option("--severity", default="info", type=click.Choice(["error", "warn", "info"]), help="Minimum severity to report (error, warn, info)")
@click.option("--no-llm", is_flag=True, help="Skip LLM consequences")
@click.option("--rule-id", default=None, help="Run only this rule ID")
@click.option("--confirm-read-warnings", is_flag=True, help="Acknowledge warnings, allow commit to proceed")
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings):
    """Check files for convention violations."""
    from enforcer.types import Severity

    config = load_config(config_path)
    if rule_id:
        config.rules = [r for r in config.rules if r.id == rule_id]
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
    output = reporter.render(all_matches, severity_actions=config.severity_actions)
    click.echo(output)
    sys.exit(reporter.exit_code(all_matches, severity_actions=config.severity_actions, confirm_warnings=confirm_read_warnings))

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

@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing hook")
def install(force):
    """Install pre-commit hook into .git/hooks/pre-commit."""
    import shutil

    hook_path = os.path.join(".git", "hooks", "pre-commit")
    if os.path.exists(hook_path) and not force:
        click.echo(f"Hook already exists at {hook_path}. Use --force to overwrite.")
        sys.exit(1)

    hook_source = os.path.join(os.path.dirname(__file__), "..", "scripts", "pre-commit-hook")
    hook_source = os.path.normpath(hook_source)
    shutil.copy(hook_source, hook_path)
    os.chmod(hook_path, 0o755)
    click.echo(f"Installed pre-commit hook to {hook_path}")

if __name__ == "__main__":
    cli()
