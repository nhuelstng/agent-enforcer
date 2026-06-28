"""AllowlistMatcher: checks file content against an allowlist from another file (read_target)."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from typing import Callable
from enforcer.types import Match, FileContext, Needs

@dataclass
class AllowlistMatcher:
    """Reads an allowlist file (read_target), extracts entries via an extractor function, checks if file content violates the allowlist."""
    extractor: Callable[[str], set[str]]
    consumer: Callable[[str], set[str]]
    read_target: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file content entries not present in the allowlist. Returns list of Match."""
        from enforcer.rule import _glob_match
        shared_ctx = shared_ctx or {}
        target_ctx = shared_ctx.get(self.read_target)
        if not target_ctx:
            for key, ctx in shared_ctx.items():
                if _glob_match(key, self.read_target):
                    target_ctx = ctx
                    break
        if not target_ctx:
            return []
        if file_ctx.raw is None or target_ctx.raw is None:
            return []
        allowed = self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        undefined = used - allowed
        return [
            Match(file=file_ctx.path, line=0, matched_value=item)
            for item in undefined
        ]
