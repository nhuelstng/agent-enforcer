"""CommitMessageMatcher: checks commit message against a required pattern."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.git import Git

@dataclass
class CommitMessageMatcher:
    """Flags if the commit message (first line) doesn't match the required pattern.
    Reads from ENFORCER_COMMIT_MSG_FILE env var (set by commit-msg hook), falling back
    to .git/COMMIT_EDITMSG. Skips merge commits.

    What:       flags the commit message when its first line doesn't match `pattern`
    Ignores:    merge commits (first line starts with "Merge"); missing message file; unreadable files; messages that match
    Basis:      RAW (commit subject via the git seam)
    shared_ctx: none (defensive default only)
    """
    pattern: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag commit message if its first line doesn't match the required pattern. Returns list of Match."""
        subject = Git(self.workspace).commit_subject()
        if subject is None or subject.startswith("Merge"):
            return []

        if self._compiled.search(subject):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=subject,
        )]
