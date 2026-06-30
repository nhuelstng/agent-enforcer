"""CharCountMatcher: checks file character count against a predicate."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CharCountMatcher:
    """Counts characters in file, emits a match if the count fails the predicate.

    What:       flags any file whose character count exceeds `max_chars`
    Ignores:    empty files (raw is None); files at or below the threshold
    Basis:      RAW (len() of file_ctx.raw)
    shared_ctx: none (defensive default only)
    """
    max_chars: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file if character count exceeds the configured maximum. Returns list of Match."""
        if file_ctx.raw is None:
            return []
        count = len(file_ctx.raw)
        if count > self.max_chars:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
