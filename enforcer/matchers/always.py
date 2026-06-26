from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AlwaysMatcher:
    matched_value: str = "(always)"
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        return [Match(file=file_ctx.path, line=1, matched_value=self.matched_value)]
