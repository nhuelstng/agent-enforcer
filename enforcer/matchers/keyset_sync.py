"""KeySetSyncMatcher: cross-file key-set sync. Keys in source must appear in target files."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.extractors.core import Extractor
from enforcer.types import Match, FileContext, Needs
from enforcer.check_context import CheckContext
from enforcer.glob_util import glob_match


@dataclass
class KeySetSyncMatcher:
    """Cross-file key-set sync. Keys extracted from this file via source_extractor
    must appear (after exclude_keys removal) in the union of keys extracted from
    target files via target_extractor. Emits one Match per missing key.

    Target files are resolved from the CheckContext's read-target cache by
    glob-matching their paths. No direct file I/O — fully testable via an
    injected context.

    What:       flags keys present in source (via source_extractor, minus exclude_keys) but absent from the union of target file keys
    Ignores:    empty files (raw falsy); the source file itself; exclude_keys; keys present in targets
    Basis:      RAW (extracts from file_ctx.raw and target_ctx.raw; cross-file via read-target glob lookup)
    shared_ctx: reads target FileContexts (ctx.files) by glob match against target_globs
    """
    source_extractor: Extractor
    target_extractor: Extractor
    target_globs: list[str]
    exclude_keys: set[str] = field(default_factory=set)
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Extract keys from source, check against union of target file keys, emit matches for missing keys."""
        if not file_ctx.raw:
            return []
        used = self.source_extractor.extract(file_ctx.raw) - self.exclude_keys
        allowed = self._collect_target_keys(CheckContext.of(shared_ctx), file_ctx.path)
        return [
            Match(file=file_ctx.path, line=0, matched_value=key)
            for key in sorted(used - allowed)
        ]

    def _collect_target_keys(self, ctx: CheckContext, source_path: str) -> set[str]:
        """Collect the union of keys extracted from all matching target files."""
        allowed: set[str] = set()
        for glob in self.target_globs:
            for _, target_ctx in self._matching_targets(glob, ctx, source_path):
                allowed |= self._extract_if_raw(target_ctx)
        return allowed

    def _extract_if_raw(self, ctx: FileContext) -> set[str]:
        """Extract keys from ctx if it has raw text, else empty set."""
        if not ctx.raw:
            return set()
        return self.target_extractor.extract(ctx.raw)

    def _matching_targets(self, glob: str, ctx: CheckContext, source_path: str):
        """Yield (path, FileContext) read targets matching the glob, skipping the source file itself."""
        for key, target_ctx in ctx.files.items():
            if key == source_path:
                continue
            if glob_match(key, glob):
                yield key, target_ctx

    def __post_init__(self):
        """Validate target_globs is non-empty; empty list would emit a match for every source key."""
        if not self.target_globs:
            raise ValueError("target_globs must be non-empty — empty list emits a match for every source key")
