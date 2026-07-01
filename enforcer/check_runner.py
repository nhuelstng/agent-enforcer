"""Shared check pipeline: file collection, context building, rule execution. Used by cli.py and mcp_server.py."""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path

_JUNK_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
               "*.egg-info"}


def _glob_any_match(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)


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

    changed: set[int] = set()
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            m = re.search(r'\+(\d+)(?:,(\d+))?', line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                for i in range(start, start + count):
                    changed.add(i)
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


def build_change_context(ws: str, status_map: dict[str, str]) -> "ChangeContext":
    """Build ChangeContext from git metadata + status_map. Reads commit msg + branch."""
    from enforcer.types import ChangeContext

    commit_msg = ""
    msg_file = os.environ.get("ENFORCER_COMMIT_MSG_FILE")
    if msg_file:
        msg_path = Path(msg_file)
    else:
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


def collect_files(staged: bool, all_files: bool, paths: tuple, ws: str, base_ref: str | None = None) -> tuple[list[str], dict[str, str]]:
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


def build_shared_ctx(config, builder, ws: str) -> dict:
    """Build shared context dict from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:
                    shared_ctx[rel] = builder.build(rel)
    return shared_ctx


def run_checks(runner, builder, file_list: list[str], shared_ctx: dict, ws: str, staged: bool,
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
