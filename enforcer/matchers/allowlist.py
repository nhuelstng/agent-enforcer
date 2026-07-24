"""AllowlistMatcher: checks file content against an allowlist from another file (read_target)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from enforcer.types import Match, FileContext, Needs
from enforcer.check_context import CheckContext
from enforcer.glob_util import glob_match

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
        target_ctxs = self._resolve_targets(CheckContext.of(shared_ctx))
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

    def _resolve_targets(self, ctx: CheckContext) -> list[FileContext]:
        """Resolve read-target FileContexts by exact path or glob match."""
        files = ctx.files
        if self.read_target in files:
            return [files[self.read_target]]
        return [
            file_ctx for key, file_ctx in files.items()
            if glob_match(key, self.read_target)
        ]
