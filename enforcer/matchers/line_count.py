from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class LineCountMatcher:
    max_lines: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        count = len(file_ctx.raw.splitlines())
        if count > self.max_lines:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
