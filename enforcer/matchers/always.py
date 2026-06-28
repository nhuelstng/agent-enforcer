"""AlwaysMatcher: always matches, emits a single Match. Useful for rules that need LLM review on every file."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AlwaysMatcher:
    """Always emits one match. Typically used with an LLM consequence to trigger review on every matching file."""
    matched_value: str = "(always)"
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if file_ctx.raw is None:
            return []
        return [Match(file=file_ctx.path, line=1, matched_value=self.matched_value)]
