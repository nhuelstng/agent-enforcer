"""Command-line interface: check, docs, install commands."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
import click
from enforcer.config import load_config
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter
from enforcer.ignore import load_enforcerignore, is_ignored
from enforcer.check_runner import (
    _glob_any_match,
    _parse_diff_changed_lines,
    _parse_name_status,
    build_change_context as _build_change_context,
    collect_files as _collect_files,
    build_shared_ctx as _build_shared_ctx,
    run_checks as _run_checks,
)

_JUNK_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
               "*.egg-info"}

@click.group()
def cli():
    """Convention enforcement tool for coding agents."""
    pass

def _assert_output_contained(output: str, ws: str) -> None:
    """Reject --output paths escaping the workspace. Prevents arbitrary file writes."""
    output_resolved = Path(output).resolve()
    ws_resolved = Path(ws).resolve()
    if not output_resolved.is_relative_to(ws_resolved):
        click.echo("Error: --output path must be within workspace.", err=True)
        sys.exit(2)

@cli.command()
@click.argument("files", nargs=-1)
@click.option("--staged", is_flag=True, help="Check staged files only")
@click.option("--all", "all_files", is_flag=True, help="Check entire repo")
@click.option("--paths", multiple=True, help="Check specific files")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text", "sarif"]), help="Output format: text, json, or sarif")
@click.option("--config", "config_path", default="enforcer_config", help="Path to enforcer config (file or package)")
@click.option("--workspace", default=None, help="Global workspace root")
@click.option("--severity", default="info", type=click.Choice(["error", "warn", "info"]), help="Minimum severity to report (error, warn, info)")
@click.option("--no-llm", is_flag=True, help="Skip LLM consequences")
@click.option("--rule-id", default=None, help="Run only this rule ID")
@click.option("--confirm-read-warnings", is_flag=True, help="Acknowledge warnings, allow commit to proceed")
@click.option("--fix", is_flag=True, help="Apply auto-fixes where available")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
@click.option("--base-ref", default=None, help="Git ref to diff against (e.g. origin/master). Sets changed_lines so diff_only rules fire in CI.")
def check(files, staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings, fix, output, base_ref):
    """Check files for convention violations.

    Positional FILES are treated like --paths, so pre-commit (which passes staged
    filenames positionally) works out of the box: `enforcer check a.py b.py`.
    """
    from enforcer.types import Severity

    # Positional args and --paths are the same "specific files" mode; merge them.
    paths = tuple(paths) + tuple(files)

    exclusive = sum([bool(staged), bool(base_ref), bool(all_files)])
    if exclusive > 1:
        click.echo("Error: --staged, --base-ref, and --all are mutually exclusive.", err=True)
        sys.exit(2)
    if paths and (staged or base_ref or all_files):
        click.echo("Error: --paths cannot be combined with --staged, --base-ref, or --all.", err=True)
        sys.exit(2)

    config = load_config(config_path)
    # The full rule set is what the on-disk conventions doc reflects. Capture it
    # before --rule-id narrows the run set, so the doc-staleness check (rendered
    # below) compares against the complete doc, not a single-rule subset —
    # otherwise `--rule-id` spuriously trips `conventions-md-stale`.
    all_rules = list(config.rules)
    if rule_id:
        config.rules = [r for r in config.rules if r.id == rule_id]
    ws = workspace or config.workspace

    file_list, status_map = _collect_files(staged, all_files, paths, ws, base_ref=base_ref)

    ignore_patterns = load_enforcerignore(ws) if not staged else []
    if ignore_patterns:
        file_list = [f for f in file_list if not is_ignored(f, ignore_patterns)]

    sev_map = {"error": Severity.ERROR, "warn": Severity.WARN, "info": Severity.INFO}

    runner = RuleRunner(
        config.rules,
        workspace=ws,
        no_llm=no_llm,
        min_severity=sev_map[severity],
        llm_config=config.llm_config,
    )

    builder = FileContextBuilder(config.rules, workspace=ws)
    from enforcer.docs import render_rules_doc
    rendered_doc = render_rules_doc(all_rules, workspace=config.workspace or ws)
    shared_ctx = _build_shared_ctx(config, builder, ws, staged_files=file_list, rendered_doc=rendered_doc)

    change_ctx = _build_change_context(ws, status_map)
    shared_ctx["__change__"] = change_ctx
    shared_ctx["__llm_enabled__"] = not no_llm
    shared_ctx["__llm_config__"] = config.llm_config

    all_matches = _run_checks(runner, builder, file_list, shared_ctx, ws, staged,
                              diff_ref=base_ref, status_map=status_map)

    meta_matches = runner.run_metadata_rules(shared_ctx)
    all_matches.extend(meta_matches)

    cross_matches = runner.run_cross_file_finalizers(shared_ctx)
    all_matches.extend(cross_matches)

    if fix:
        from enforcer.fix import apply_fixes
        fix_providers = {r.id: r.fix for r in config.rules if r.fix is not None}
        results = apply_fixes(all_matches, ws, fix_providers)
        total_fixes = sum(r.fixes_applied for r in results)
        if total_fixes > 0:
            click.echo(f"Applied {total_fixes} fix(es) across {len(results)} file(s).", err=True)

    reporter = Reporter(format=fmt)
    output_text = reporter.render(all_matches, severity_actions=config.severity_actions, confirm_warnings=confirm_read_warnings)
    if output:
        _assert_output_contained(output, ws)
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_text)
    else:
        click.echo(output_text)
    sys.exit(reporter.exit_code(all_matches, severity_actions=config.severity_actions, confirm_warnings=confirm_read_warnings))

@cli.command()
@click.option("--config", "config_path", default="enforcer_config")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
def docs(config_path, output):
    """Generate markdown documentation of all configured rules."""
    from enforcer.docs import render_rules_markdown

    config = load_config(config_path)
    md = render_rules_markdown(config.rules)
    if output:
        ws = config.workspace
        if not ws or ws == ".":
            ws = str(Path(config_path).resolve().parent)
        _assert_output_contained(output, ws)
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        click.echo(f"Documentation written to {output}")
    else:
        click.echo(md)

@cli.command(name="sync-doc")
@click.option("--config", "config_path", default="enforcer_config")
@click.option("--output", "-o", default="CONVENTIONS.md")
def sync_doc(config_path, output):
    """Regenerate the natural-language conventions doc from configured rules."""
    from enforcer.docs import render_rules_doc

    config = load_config(config_path)
    fresh = render_rules_doc(config.rules, workspace=config.workspace)

    ws = config.workspace
    if not ws or ws == ".":
        ws = str(Path(config_path).resolve().parent)
    _assert_output_contained(output, ws)
    Path(output).write_text(fresh, encoding="utf-8")
    click.echo(f"Wrote {output}")

@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing hooks")
def install(force):
    """Install commit-msg hook."""
    import shutil

    hooks_dir = os.path.join(".git", "hooks")
    # Hooks ship as package data under enforcer/hooks/ so the install
    # command works for pip/wheel installs, not just editable checkouts.
    hooks_src_dir = os.path.join(os.path.dirname(__file__), "hooks")

    hooks = [
        ("commit-msg", "commit-msg-hook"),
    ]
    for hook_name, script_name in hooks:
        hook_path = os.path.join(hooks_dir, hook_name)
        if os.path.exists(hook_path) and not force:
            click.echo(f"Hook already exists at {hook_path}. Use --force to overwrite.")
            sys.exit(1)
        hook_source = os.path.join(hooks_src_dir, script_name)
        if not os.path.exists(hook_source):
            click.echo(f"Hook source not found at {hook_source}. The wheel may be missing package data.", err=True)
            sys.exit(1)
        shutil.copy(hook_source, hook_path)
        os.chmod(hook_path, 0o755)
        click.echo(f"Installed {hook_name} hook to {hook_path}")

@cli.command()
@click.argument("rule_id")
@click.option("--config", "config_path", default="enforcer_config")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]))
def explain(rule_id, config_path, fmt):
    """Explain what a rule matches, what it ignores, and show a worked example."""
    from enforcer.explain import load_rule_for_explain, render_rule_explainer, render_rule_explainer_json

    result = load_rule_for_explain(config_path, rule_id)
    if result.rule is None:
        click.echo(f"No rule with id '{rule_id}' found.", err=True)
        if result.suggestions:
            click.echo("Did you mean one of: " + ", ".join(result.suggestions) + "?", err=True)
        sys.exit(1)

    if fmt == "json":
        import json
        click.echo(json.dumps(render_rule_explainer_json(result.rule, workspace=result.config_workspace), indent=2))
    else:
        click.echo(render_rule_explainer(result.rule, workspace=result.config_workspace))


if __name__ == "__main__":
    cli()
