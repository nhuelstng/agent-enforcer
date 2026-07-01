"""AllowlistMatcher: checks file content against an allowlist from another file (read_target)."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from typing import Callable
from enforcer.types import Match, FileContext, Needs

@dataclass
class AllowlistMatcher:
    """Reads an allowlist file (read_target), extracts entries via an extractor function, checks if file content violates the allowlist.

    What:       flags entries found in file content (via `consumer`) that are absent from the allowlist (via `extractor` on read_target)
    Ignores:    files with no read_target context in shared_ctx; files with raw=None; allowlisted entries
    Basis:      RAW (extracts from file_ctx.raw and target_ctx.raw)
    shared_ctx: reads read_target FileContext(s) by exact key or glob match
    """
    extractor: Callable[[str], set[str]]
    consumer: Callable[[str], set[str]]
    read_target: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag file content entries not present in the allowlist. Returns list of Match."""
        from enforcer.rule import _glob_match
        shared_ctx = shared_ctx or {}
        target_ctxs = self._resolve_targets(shared_ctx)
        if not target_ctxs or file_ctx.raw is None:
            return []
        allowed: set[str] = set()
        for target_ctx in target_ctxs:
            if target_ctx.raw is not None:
                allowed |= self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        return [
            Match(file=file_ctx.path, line=0, matched_value=item)
            for item in used - allowed
        ]

    def _resolve_targets(self, shared_ctx: dict) -> list[FileContext]:
        """Resolve target FileContexts by exact key or glob match."""
        from enforcer.rule import _glob_match
        if self.read_target in shared_ctx:
            return [shared_ctx[self.read_target]]
        return [
            ctx for key, ctx in shared_ctx.items()
            if _glob_match(key, self.read_target)
        ]
