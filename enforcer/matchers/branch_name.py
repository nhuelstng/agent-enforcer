"""BranchNameMatcher: checks current git branch against a required pattern."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.git import Git

@dataclass
class BranchNameMatcher:
    """Flags if the current git branch name doesn't match the required pattern.
    Set allow_branches to skip check for specific branches (main, master, develop).

    What:       flags the current git branch when it doesn't match `pattern`
    Ignores:    allow_branches (default main/master/develop); detached HEAD; git failures (returns empty)
    Basis:      RAW (current branch via the git seam)
    shared_ctx: none (defensive default only)
    """
    pattern: str
    allow_branches: list[str] = field(default_factory=lambda: ["main", "master", "develop"])
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag current git branch if it doesn't match the required pattern. Returns list of Match."""
        branch = Git(self.workspace).current_branch()
        if not branch or branch in self.allow_branches or branch == "HEAD":
            return []

        if self._compiled.search(branch):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=branch,
        )]
