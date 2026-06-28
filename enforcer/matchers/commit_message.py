"""CommitMessageMatcher: checks commit message against a required pattern."""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CommitMessageMatcher:
    """Flags if the commit message (first line) doesn't match the required pattern.
    Reads from .git/COMMIT_EDITMSG. Skips merge commits."""
    pattern: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        ws = self.workspace
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
