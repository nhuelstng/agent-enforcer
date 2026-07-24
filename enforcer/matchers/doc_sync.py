"""DocSyncMatcher: flags if the on-disk generated conventions doc differs from a fresh render."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext, Needs
from enforcer.check_context import CheckContext


@dataclass
class DocSyncMatcher:
    """Flags if the on-disk generated doc differs from a fresh render.

    Reads the freshly rendered doc from the CheckContext's rendered_doc slot
    (populated by the runner via render_rules_doc). Reads the on-disk doc
    from self.doc_path. No imports from io or core layers — the matcher
    is pure: read file, compare to string.

    What:       flags when the on-disk doc at `doc_path` differs from the CheckContext rendered_doc
    Ignores:    matching renders (no diff); unreadable/missing doc files (treated as empty, will flag if render is non-empty)
    Basis:      RAW (compares on-disk file text to the rendered doc string)
    shared_ctx: reads rendered_doc (via CheckContext)
    """
    doc_path: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag when the on-disk conventions doc differs from the freshly rendered one."""
        fresh = CheckContext.of(shared_ctx).rendered_doc
        try:
            on_disk = Path(self.doc_path).read_text(encoding="utf-8") if Path(self.doc_path).exists() else ""
        except OSError:
            on_disk = ""
        if on_disk != fresh:
            return [Match(file=file_ctx.path, line=0,
                          message="CONVENTIONS.md is stale or missing.", matched_value=self.doc_path)]
        return []
