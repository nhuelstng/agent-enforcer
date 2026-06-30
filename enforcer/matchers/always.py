"""AlwaysMatcher: always matches, emits a single Match. Useful for rules that need LLM review on every file."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AlwaysMatcher:
    """Always emits one match. Typically used with an LLM consequence to trigger review on every matching file.

    What:       flags every file it runs on (always emits one Match with matched_value)
    Ignores:    files with raw=None (no content to review)
    Basis:      RAW (checks file_ctx.raw is not None; no further parsing)
    shared_ctx: none (defensive default only)
    """
    matched_value: str = "(always)"
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Always emit one match for the file. Returns list of Match."""
        if file_ctx.raw is None:
            return []
        return [Match(file=file_ctx.path, line=0, matched_value=self.matched_value)]
