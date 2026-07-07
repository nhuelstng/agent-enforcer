"""SharedCtxKeyAllowlistMatcher: flags shared_ctx accesses for keys not in a declared allowlist."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs

_ACCESS_RE = re.compile(
    r'shared_ctx\s*(?:\.get\s*\(\s*|[\[\(]\s*)["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
)


@dataclass
class SharedCtxKeyAllowlistMatcher:
    """Scans source for shared_ctx.get("...") and shared_ctx["..."] accesses, flags keys not in allowlist.

    What:       flags shared_ctx accesses whose key is not in `allowed_keys`
    Ignores:    files with raw=None; accesses to declared keys; lines with no shared_ctx access
    Basis:      RAW (regex scan of file_ctx.raw)
    shared_ctx: none (defensive default only)
    """
    allowed_keys: set[str] = field(default_factory=set)
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag undeclared shared_ctx key accesses. Returns list of Match."""
        if file_ctx.raw is None:
            return []
        matches: list[Match] = []
        for i, line in enumerate(file_ctx.raw.splitlines(), start=1):
            matches.extend(self._flag_line(file_ctx.path, i, line))
        return matches

    def _flag_line(self, path: str, line_no: int, line: str) -> list[Match]:
        """Return matches for undeclared keys on a single line."""
        out: list[Match] = []
        for key in _ACCESS_RE.findall(line):
            if key in self.allowed_keys:
                continue
            out.append(Match(file=path, line=line_no, matched_value=key))
        return out
