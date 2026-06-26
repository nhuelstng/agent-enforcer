from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Pattern
from enforcer.types import Match, FileContext, Needs

@dataclass
class RegexMatcher:
    pattern: str | Pattern
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        matches: list[Match] = []
        if not file_ctx.raw:
            return matches
        for i, line in enumerate(file_ctx.raw.splitlines(), 1):
            for m in re.finditer(self.pattern, line):
                matches.append(Match(
                    file=file_ctx.path,
                    line=i,
                    column=m.start() + 1,
                    matched_value=m.group(),
                ))
        return matches
