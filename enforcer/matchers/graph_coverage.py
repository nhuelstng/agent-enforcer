"""GraphCoverageMatcher: flags public symbols missing from ONTOLOGY.md (two-phase finalizer)."""
from __future__ import annotations
import json
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class GraphCoverageMatcher:
    """Two-phase finalizer: flags public symbols present in code but absent from the rendered graph.

    Phase 1 (find): no-op. Exists only so the runner registers the finalizer.
    The public-symbol set is populated by ConceptGraphBuilder into
    shared_ctx["__public_symbols__"] during the graph build.

    Phase 2 (finalize_duplicates): compare shared_ctx["__public_symbols__"]
    against the concept names in shared_ctx["__rendered_ontology__"].
    Emit a match per symbol present in code but absent from the rendered graph.

    What:       flags public symbols (from __public_symbols__) not present in __rendered_ontology__ JSON
    Ignores:    private symbols (not in __public_symbols__); empty __rendered_ontology__ (skips silently)
    Basis:      AST_PY (declared for runner registration; find() is a no-op, finalize reads shared_ctx)
    shared_ctx: reads __public_symbols__ and __rendered_ontology__
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """No-op. Exists only so the runner registers the finalizer. Returns empty list."""
        return []

    def finalize_duplicates(self, shared_ctx: dict) -> list[Match]:
        """Emit matches for public symbols missing from the rendered graph. Returns list of Match."""
        rendered = shared_ctx.get("__rendered_ontology__", "")
        if not rendered:
            return []
        public_symbols: set[str] = shared_ctx.get("__public_symbols__", set())
        if not public_symbols:
            return []
        try:
            data = json.loads(rendered)
            graph_symbols = set(data.get("symbols", {}).keys())
        except (json.JSONDecodeError, TypeError):
            return []
        missing = public_symbols - graph_symbols
        return [
            Match(file="ONTOLOGY.md", line=0, matched_value=sym)
            for sym in sorted(missing)
        ]
