"""AllSortedMatcher: flags __all__ lists that are not alphabetically sorted."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class AllSortedMatcher:
    """Parses __all__ = [...] lists, flags non-alphabetical ordering.

    What:       flags __all__ lists where entries are not in alphabetical order
    Ignores:    files without __all__; __all__ that is already sorted
    Basis:      RAW (regex-extracts __all__ = [...] list from file_ctx.raw)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag __all__ lists that are not alphabetically sorted. Returns list of Match."""
        if not file_ctx.raw:
            return []
        matches: list[Match] = []
        for m in re.finditer(r'__all__\s*=\s*\[([^\]]*)\]', file_ctx.raw, re.DOTALL):
            list_body = m.group(1)
            entries = re.findall(r'["\']([^"\']+)["\']', list_body)
            if len(entries) < 2:
                continue
            for i in range(1, len(entries)):
                if entries[i] < entries[i - 1]:
                    line = file_ctx.raw[:m.start()].count("\n") + 1
                    matches.append(Match(
                        file=file_ctx.path,
                        line=line,
                        matched_value=entries[i],
                    ))
                    break
        return matches
