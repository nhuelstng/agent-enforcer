"""CommitMessageMatcher: checks commit message against a required pattern."""
from __future__ import annotations
import os
import re
from pathlib import Path
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommitMessageMatcher:
    """Flags if the commit message (first line) doesn't match the required pattern.
    Reads from ENFORCER_COMMIT_MSG_FILE env var (set by commit-msg hook), falling back
    to .git/COMMIT_EDITMSG. Skips merge commits.

    What:       flags the commit message when its first line doesn't match `pattern`
    Ignores:    merge commits (first line starts with "Merge"); missing message file; unreadable files; messages that match
    Basis:      RAW (regex on first line of commit message file)
    shared_ctx: none (defensive default only)
    """
    pattern: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag commit message if its first line doesn't match the required pattern. Returns list of Match."""
        ws = self.workspace
        # ponytail: ENFORCER_COMMIT_MSG_FILE is set by commit-msg hook, points to git's message file.
        # COMMIT_EDITMSG fallback covers standalone invocation (no hook installed).
        msg_file = os.environ.get("ENFORCER_COMMIT_MSG_FILE")
        if msg_file:
            msg_path = Path(msg_file)
        else:
            msg_path = Path(ws, ".git", "COMMIT_EDITMSG")
        if not msg_path.exists():
            return []
        try:
            content = msg_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        lines = content.splitlines()
        first_line = lines[0] if lines else ""

        if first_line.startswith("Merge"):
            return []

        if self._compiled.search(first_line):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=first_line,
        )]
