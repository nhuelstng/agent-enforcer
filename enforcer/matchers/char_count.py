"""CharCountMatcher: checks file character count against a predicate."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CharCountMatcher:
    """Counts characters in file, emits a match if the count fails the predicate."""
    max_chars: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if file_ctx.raw is None:
            return []
        count = len(file_ctx.raw)
        if count > self.max_chars:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
