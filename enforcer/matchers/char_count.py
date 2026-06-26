from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class CharCountMatcher:
    max_chars: int
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        count = len(file_ctx.raw)
        if count > self.max_chars:
            return [Match(file=file_ctx.path, line=0, matched_value=str(count))]
        return []
