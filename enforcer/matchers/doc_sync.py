"""DocSyncMatcher: flags if the on-disk generated conventions doc differs from a fresh render."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext, Needs


@dataclass
class DocSyncMatcher:
    """Flags if the on-disk generated doc differs from a fresh render.

    Reads config rules from shared_ctx["__rules__"] (set by the CLI runner),
    falling back to load_config(self.config_path) when called standalone.
    Reads the doc file from self.doc_path on disk.

    What:       flags when the on-disk doc at `doc_path` differs from a fresh render of the current rules
    Ignores:    matching renders (no diff); unreadable/missing doc files (treated as empty, will flag if render is non-empty)
    Basis:      RAW (renders rules to markdown, compares to on-disk file text)
    shared_ctx: reads `__rules__`, `__workspace__`
    """
    config_path: str
    doc_path: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        rules = shared_ctx.get("__rules__")
        workspace = shared_ctx.get("__workspace__", ".")
        if rules is None:
            from enforcer.config import load_config
            config = load_config(self.config_path)
            rules = config.rules
            workspace = config.workspace or "."
        from enforcer.docs import render_rules_doc
        fresh = render_rules_doc(rules, workspace=workspace)
        try:
            on_disk = Path(self.doc_path).read_text(encoding="utf-8") if Path(self.doc_path).exists() else ""
        except OSError:
            on_disk = ""
        if on_disk != fresh:
            return [Match(file=file_ctx.path, line=0, rule_id="conventions-md-stale",
                          message="CONVENTIONS.md is stale or missing.", matched_value=self.doc_path)]
        return []
