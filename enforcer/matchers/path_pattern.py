from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class PathNotMatchingMatcher:
    pattern: str
    needs: Needs | None = None

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not fnmatch.fnmatch(file_ctx.path, self.pattern):
            return [Match(file=file_ctx.path, line=0, matched_value=file_ctx.path)]
        return []
