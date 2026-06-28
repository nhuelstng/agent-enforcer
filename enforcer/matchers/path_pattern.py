"""PathNotMatchingMatcher: ensures file path does NOT match a glob pattern."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class PathNotMatchingMatcher:
    """Emits a match if the file path matches the given glob. Used to enforce path conventions via Not combinator."""
    pattern: str
    needs: Needs | None = None

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not fnmatch.fnmatch(file_ctx.path, self.pattern):
            return [Match(file=file_ctx.path, line=0, matched_value=file_ctx.path)]
        return []
