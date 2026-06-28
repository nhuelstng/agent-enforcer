"""LineCountMatcher: checks file line count against a predicate."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class LineCountMatcher:
    """Counts lines in file, emits a match if the count fails the predicate."""
    max_lines: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file if line count exceeds the configured maximum. Returns list of Match."""
        if file_ctx.raw is None:
            return []
        count = len(file_ctx.raw.splitlines())
        if count > self.max_lines:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
