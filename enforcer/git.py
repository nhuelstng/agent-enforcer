"""Git: the single seam for all git access — subprocess invocation and output parsing.

One adapter per repo root. Callers (check_runner, BranchNameMatcher, CommitMessageMatcher)
depend on this interface, not on subprocess; a test can substitute a fake Git instead of
running `git init`. Every method fails soft: an absent repo, a detached HEAD, or a git
error yields the empty/None result, never an exception.
"""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

_HUNK_RE = re.compile(r"\+(\d+)(?:,(\d+))?")


@runtime_checkable
class GitPort(Protocol):
    """The git operations the enforcer depends on — the seam a fake satisfies in tests.

    Two adapters justify the seam: the real subprocess-backed Git in production, and an
    in-memory fake in a test that would otherwise shell out to `git init`."""
    def changed_files(self, staged: bool = False, ref: str | None = None) -> tuple[list[str], dict[str, str]]:
        """Return (files, status_map) for the staged index or a `<ref>...HEAD` diff."""
        ...
    def changed_lines(self, path: str, ref: str | None = None) -> set[int] | None:
        """Return one file's added line numbers, or None when no diff is available."""
        ...
    def current_branch(self) -> str:
        """Return the current branch, "HEAD" when detached, or "" when unavailable."""
        ...
    def commit_subject(self) -> str | None:
        """Return the pending commit message's first line, or None when there is none."""
        ...


def added_lines(diff_output: str) -> set[int]:
    """Return every added line number across the `@@ ... @@` hunk headers of a unified diff."""
    changed: set[int] = set()
    for line in diff_output.splitlines():
        if not line.startswith("@@"):
            continue
        m = _HUNK_RE.search(line)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) else 1
        changed.update(range(start, start + count))
    return changed


def parse_name_status(diff_output: str) -> tuple[list[str], dict[str, str]]:
    """Parse `git diff --name-status` output into (file_list, status_map).

    Status letters: A=added, M=modified, D=deleted, R=renamed (new path), C=copy
    (treated as added). Renames/copies use the destination path (third column)."""
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
            path, status = parts[2], "renamed"
        elif letter == "C" and len(parts) >= 3:
            path, status = parts[2], "added"
        else:
            path = parts[1]
            status = {"A": "added", "M": "modified", "D": "deleted"}.get(letter, "modified")
        files.append(path)
        status_map[path] = status
    return files, status_map


class Git(GitPort):
    """Git access for one repo root: changed files/lines, current branch, commit subject.

    The single place that shells out to git or reads `.git/` files, so no caller ever
    constructs a git command. Subprocess invocation and git-output parsing (name-status,
    diff hunks) live here; merge-commit filtering stays the caller's policy since callers
    differ on it."""

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root

    def _run(self, *args: str) -> str | None:
        """Run `git <args>` in the repo root; return stdout, or None on any failure."""
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True, text=True, cwd=self.repo_root,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout

    def changed_files(self, staged: bool = False, ref: str | None = None) -> tuple[list[str], dict[str, str]]:
        """Return (files, status_map) from `git diff --name-status`.

        staged=True diffs the index (--cached); ref diffs `<ref>...HEAD`; neither yields
        empty. A git failure fails soft to ([], {})."""
        if staged:
            out = self._run("diff", "--cached", "--name-status")
        elif ref:
            out = self._run("diff", "--name-status", f"{ref}...HEAD")
        else:
            return [], {}
        return parse_name_status(out or "")

    def changed_lines(self, path: str, ref: str | None = None) -> set[int] | None:
        """Return the added line numbers for one file, or None when no diff is available.

        ref=None diffs the index (--cached); ref set diffs `<ref>...HEAD`. Returns an
        empty set when the file diffed but added no lines; None when git produced no diff."""
        scope = ["--cached"] if ref is None else [f"{ref}...HEAD"]
        out = self._run("diff", "-U0", *scope, "--", path)
        if not out:
            return None
        return added_lines(out)

    def current_branch(self) -> str:
        """Return the current branch name, "HEAD" when detached, or "" when unavailable."""
        out = self._run("rev-parse", "--abbrev-ref", "HEAD")
        return out.strip() if out else ""

    def commit_subject(self) -> str | None:
        """Return the first line of the pending commit message, or None when there is none.

        Reads ENFORCER_COMMIT_MSG_FILE (set by the commit-msg hook) when present, else
        <repo_root>/.git/COMMIT_EDITMSG. The subject may be "" (empty message) or a merge
        subject — merge filtering is left to the caller."""
        msg_file = os.environ.get("ENFORCER_COMMIT_MSG_FILE")
        msg_path = Path(msg_file) if msg_file else Path(self.repo_root, ".git", "COMMIT_EDITMSG")
        if not msg_path.exists():
            return None
        try:
            content = msg_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        lines = content.splitlines()
        return lines[0] if lines else ""
