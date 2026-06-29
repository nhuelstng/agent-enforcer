"""RegexMatcher: finds regex pattern matches in file text."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match, FileContext, Needs

@dataclass
class RegexMatcher:
    """Matches lines against a regex pattern. Returns one Match per line that matches."""
    pattern: str | Pattern
    needs: Needs = Needs.RAW
    redact: bool = False

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Find regex pattern matches line by line in file text. Returns list of Match."""
        matches: list[Match] = []
        if not file_ctx.raw:
            return matches
        for i, line in enumerate(file_ctx.raw.splitlines(), 1):
            for m in re.finditer(self.pattern, line):
                value = "***REDACTED***" if self.redact else m.group()
                matches.append(Match(
                    file=file_ctx.path,
                    line=i,
                    column=m.start() + 1,
                    matched_value=value,
                ))
        return matches
