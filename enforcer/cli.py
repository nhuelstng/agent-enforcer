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

_JUNK_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
               "*.egg-info"}

@click.group()
def cli():
    """Convention enforcement tool for coding agents."""
    pass

def _glob_any_match(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)

def _assert_output_contained(output: str, ws: str) -> None:
    """Reject --output paths escaping the workspace. Prevents arbitrary file writes."""
    output_resolved = Path(output).resolve()
    ws_resolved = Path(ws).resolve()
    if not output_resolved.is_relative_to(ws_resolved):
        click.echo("Error: --output path must be within workspace.", err=True)
        sys.exit(2)

def _parse_diff_changed_lines(repo_root: str, file_path: str, ref: str | None = None) -> set[int] | None:
    """Parse git diff -U0 for a file, return set of changed (added) line numbers.
    ref=None uses --cached (staged). ref set uses <ref>...HEAD.
    Returns None if diff can't be parsed (no diff info). Returns empty set if diff parsed but no added lines."""
    try:
        diff_cmd = ["git", "diff", "-U0"]
        diff_cmd += ["--cached"] if ref is None else [f"{ref}...HEAD"]
        diff_cmd += ["--", file_path]
        result = subprocess.run(
            diff_cmd,
            capture_output=True, text=True, cwd=repo_root,
        )
        if result.returncode != 0 or not result.stdout:
            return None
    except Exception:
        return None

    import re
    changed: set[int] = set()
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            m = re.search(r'\+(\d+)(?:,(\d+))?', line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                for i in range(start, start + count):
                    changed.add(i)
    # ponytail: return empty set (not None) when diff parsed but no added lines — distinguishes "no diff info" from "diff parsed, nothing added"
    return changed

def _parse_name_status(diff_output: str) -> tuple[list[str], dict[str, str]]:
    """Parse `git diff --name-status` output. Returns (file_list, status_map).
    Status letters: A=added, M=modified, D=deleted, R=renamed (new path), C=copy (treat as added)."""
    files: list[str] = []
    status_map: dict[str, str] = {}
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        letter = parts[0][0].upper()
        if letter == "R" and len(parts) >= 3:
            path = parts[2]
            status = "renamed"
        elif letter == "C" and len(parts) >= 3:
            path = parts[2]
            status = "added"
        else:
            path = parts[1]
            status = {"A": "added", "M": "modified", "D": "deleted"}.get(letter, "modified")
        files.append(path)
        status_map[path] = status
    return files, status_map


def _build_change_context(ws: str, status_map: dict[str, str]) -> "ChangeContext":
    """Build ChangeContext from git metadata + status_map. Reads commit msg + branch."""
    from enforcer.types import ChangeContext

    commit_msg = ""
    msg_path = Path(ws, ".git", "COMMIT_EDITMSG")
    if msg_path.exists():
        try:
            content = msg_path.read_text(encoding="utf-8", errors="replace")
            first_line = content.splitlines()[0] if content.splitlines() else ""
            if not first_line.startswith("Merge"):
                commit_msg = first_line
        except OSError:
            pass

    branch = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=ws,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass

    created = [f for f, s in status_map.items() if s == "added"]
    modified = [f for f, s in status_map.items() if s == "modified"]
    deleted = [f for f, s in status_map.items() if s == "deleted"]
    renamed = [f for f, s in status_map.items() if s == "renamed"]

    return ChangeContext(
        commit_msg=commit_msg,
        branch=branch,
        created=created,
        modified=modified,
        deleted=deleted,
        renamed=renamed,
    )


def _collect_files(staged: bool, all_files: bool, paths: tuple, ws: str, base_ref: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Collect the list of files to check based on CLI mode. Returns (file_list, status_map)."""
    if staged:
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-status"],
            stderr=subprocess.DEVNULL, cwd=ws,
        )
        return _parse_name_status(result.decode())
    if base_ref:
        result = subprocess.check_output(
            ["git", "diff", "--name-status", f"{base_ref}...HEAD"],
            stderr=subprocess.DEVNULL, cwd=ws,
        )
        return _parse_name_status(result.decode())
    if all_files:
        file_list = []
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if not _glob_any_match(d, _JUNK_DIRS)]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
        return file_list, {}
    return list(paths), {}

def _build_shared_ctx(config, builder, ws: str) -> dict:
    """Build shared context dict from rule read_targets."""
    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            if target in shared_ctx:
                continue
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                target_ctx = builder.build(rel)
                shared_ctx.setdefault(target, target_ctx)
    return shared_ctx

def _run_checks(runner, builder, file_list: list[str], shared_ctx: dict, ws: str, staged: bool,
                diff_ref: str | None = None, status_map: dict[str, str] | None = None) -> list:
    """Run rules against each file, return aggregated matches."""
    import dataclasses
    from enforcer.types import Match
    status_map = status_map or {}
    all_matches: list[Match] = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        status = status_map.get(f, "modified")
        if diff_ref is not None:
            ctx = dataclasses.replace(ctx, status=status,
                                      changed_lines=_parse_diff_changed_lines(ws, f, ref=diff_ref))
        elif staged:
            ctx = dataclasses.replace(ctx, status=status,
                                      changed_lines=_parse_diff_changed_lines(ws, f))
        else:
            if status != "modified":
                ctx = dataclasses.replace(ctx, status=status)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)
    return all_matches

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
@click.option("--fix", is_flag=True, help="Apply auto-fixes where available")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
@click.option("--base-ref", default=None, help="Git ref to diff against (e.g. origin/master). Sets changed_lines so diff_only rules fire in CI.")
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings, fix, output, base_ref):
    """Check files for convention violations."""
    from enforcer.types import Severity

    exclusive = sum([bool(staged), bool(base_ref), bool(all_files)])
    if exclusive > 1:
        click.echo("Error: --staged, --base-ref, and --all are mutually exclusive.", err=True)
        sys.exit(2)
    if paths and (staged or base_ref or all_files):
        click.echo("Error: --paths cannot be combined with --staged, --base-ref, or --all.", err=True)
        sys.exit(2)

    config = load_config(config_path)
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
    shared_ctx = _build_shared_ctx(config, builder, ws)

    change_ctx = _build_change_context(ws, status_map)
    shared_ctx["__change__"] = change_ctx
    shared_ctx["__llm_enabled__"] = not no_llm

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
    output_text = reporter.render(all_matches, severity_actions=config.severity_actions)
    if output:
        _assert_output_contained(output, ws)
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_text)
    else:
        click.echo(output_text)
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
        _assert_output_contained(output, config.workspace or ".")
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
