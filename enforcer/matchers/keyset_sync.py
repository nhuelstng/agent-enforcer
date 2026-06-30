"""KeySetSyncMatcher: cross-file key-set sync. Keys in source must appear in target files."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs


@dataclass
class KeySetSyncMatcher:
    """Cross-file key-set sync. Keys extracted from this file via source_extractor
    must appear (after exclude_keys removal) in the union of keys extracted from
    target files via target_extractor. Emits one Match per missing key.

    Target files are resolved from shared_ctx by glob-matching the keys populated
    by the runner's read_targets mechanism. No direct file I/O — fully testable
    via an injected shared_ctx dict.
    """
    source_extractor: "object"
    target_extractor: "object"
    target_globs: list[str]
    exclude_keys: set[str] = field(default_factory=set)
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Extract keys from source, check against union of target file keys, emit matches for missing keys."""
        shared_ctx = shared_ctx or {}
        if not file_ctx.raw or not shared_ctx:
            return []
        used = self.source_extractor.extract(file_ctx.raw) - self.exclude_keys
        allowed: set[str] = set()
        for glob in self.target_globs:
            for path, ctx in self._matching_targets(glob, shared_ctx, file_ctx.path):
                if ctx.raw:
                    allowed |= self.target_extractor.extract(ctx.raw)
        return [
            Match(file=file_ctx.path, line=0, matched_value=key)
            for key in sorted(used - allowed)
        ]

    def _matching_targets(self, glob, shared_ctx, source_path):
        """Yield (path, ctx) pairs from shared_ctx matching the glob, skipping __-prefixed keys and the source file itself."""
        from enforcer.rule import _glob_match
        for key, ctx in shared_ctx.items():
            if key.startswith("__"):
                continue
            if key == source_path:
                continue
            if _glob_match(key, glob):
                yield key, ctx

    def __post_init__(self):
        """Validate target_globs is non-empty; empty list would emit a match for every source key."""
        if not self.target_globs:
            raise ValueError("target_globs must be non-empty — empty list emits a match for every source key")
