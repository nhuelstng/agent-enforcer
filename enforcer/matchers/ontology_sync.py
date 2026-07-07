"""OntologySyncMatcher: flags if the on-disk ONTOLOGY.md differs from a fresh render."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enforcer.types import Match, FileContext, Needs


@dataclass
class OntologySyncMatcher:
    """Flags if the on-disk ontology graph differs from a fresh render.

    Reads the freshly rendered graph from shared_ctx["__rendered_ontology__"]
    (populated by the runner via ConceptGraphBuilder + render_ontology_markdown).
    Reads the on-disk graph from self.graph_path. Pure: read file, compare to string.

    What:       flags when the on-disk graph at `graph_path` differs from `shared_ctx["__rendered_ontology__"]`
    Ignores:    matching renders (no diff); unreadable/missing graph files (treated as empty, will flag if render is non-empty)
    Basis:      RAW (compares on-disk file text to shared_ctx string)
    shared_ctx: reads `__rendered_ontology__`
    """
    graph_path: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Compare on-disk graph to fresh render; emit Match if they differ."""
        shared_ctx = shared_ctx or {}
        fresh = shared_ctx.get("__rendered_ontology__", "")
        try:
            on_disk = Path(self.graph_path).read_text(encoding="utf-8") if Path(self.graph_path).exists() else ""
        except OSError:
            on_disk = ""
        if on_disk != fresh:
            return [Match(file=file_ctx.path, line=0,
                          message="ONTOLOGY.md is stale or missing.", matched_value=self.graph_path)]
        return []
