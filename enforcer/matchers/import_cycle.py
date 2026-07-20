"""CycleMatcher: flags import edges that lie on a dependency cycle."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class CycleMatcher:
    """Flags import statements that participate in an import cycle (A -> ... -> A).

    Complements ArchitectureMatcher. A layer DAG only prevents *cross-layer* cycles,
    and only as a byproduct of a hand-authored acyclic edge set; it never catches a
    cycle among files that share a layer (or in a codebase with no declared layers).
    This detects cycles directly from the import graph, at file granularity, for every
    language the graph covers (Py/TS/JS/Go).

    What:       flags an import edge (file -> target) when `target` can reach `file`
                back through the import graph, i.e. the edge closes a cycle
    Ignores:    acyclic edges; self-imports; unresolvable imports (absent from graph)
    Basis:      AST_PY/AST_TS/AST_GO (reads pre-built __import_graph__; line via __import_lines__)
    shared_ctx: reads __import_graph__ (dict[str, set[str]]); memoizes reachability
                under __cycle_reach__ so each source node is traversed at most once
    """
    needs: Needs = Needs.AST_PY
    reads_import_graph = True  # marker: check_runner builds __import_graph__ when present

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag each import of file_ctx.path that participates in a cycle. Returns list of Match."""
        shared_ctx = shared_ctx or {}
        graph = shared_ctx.get("__import_graph__", {})
        path = file_ctx.path
        import_lines = shared_ctx.get("__import_lines__", {}).get(path, {})
        matches: list[Match] = []
        for tgt in sorted(graph.get(path, set())):
            if tgt == path or not self._reaches(graph, tgt, path, shared_ctx):
                continue
            matches.append(Match(
                file=path,
                line=import_lines.get(tgt, 0),
                matched_value=self._describe(graph, path, tgt),
            ))
        return matches

    def _reaches(self, graph: dict, start: str, goal: str, shared_ctx: dict) -> bool:
        """True if `goal` is reachable from `start` in the import graph."""
        return goal in self._reachable_from(graph, start, shared_ctx)

    @staticmethod
    def _reachable_from(graph: dict, start: str, shared_ctx: dict) -> set[str]:
        """BFS-reachable node set from `start`, memoized in shared_ctx by source node."""
        cache: dict[str, set[str]] = shared_ctx.setdefault("__cycle_reach__", {})
        if start in cache:
            return cache[start]
        seen: set[str] = set()
        queue: deque[str] = deque(graph.get(start, ()))
        while queue:
            node = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            queue.extend(graph.get(node, ()))
        cache[start] = seen
        return seen

    @staticmethod
    def _describe(graph: dict, src: str, tgt: str) -> str:
        """Render the cycle 'src -> tgt -> ... -> src' via a shortest path tgt->src."""
        prev = CycleMatcher._shortest_prev(graph, start=tgt, stop=src)
        seq = [src]
        while seq[-1] != tgt:
            seq.append(prev[seq[-1]])
        seq.reverse()  # tgt -> ... -> src
        return " -> ".join([src, *seq])

    @staticmethod
    def _shortest_prev(graph: dict, start: str, stop: str) -> dict[str, str]:
        """BFS predecessor map from `start`, stopping once `stop` is dequeued."""
        prev: dict[str, str] = {start: start}
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            if node == stop:
                break
            CycleMatcher._extend_prev(graph, node, prev, queue)
        return prev

    @staticmethod
    def _extend_prev(graph: dict, node: str, prev: dict, queue: deque) -> None:
        """Record `node` as predecessor of each unseen neighbour and enqueue it."""
        for nxt in graph.get(node, ()):
            if nxt in prev:
                continue
            prev[nxt] = node
            queue.append(nxt)
