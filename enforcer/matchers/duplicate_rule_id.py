"""DuplicateRuleIdMatcher: flags config files where the same Rule id appears more than once."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class DuplicateRuleIdMatcher:
    """Scans for id="..." values that appear more than once in a config file.

    What:       flags Rule id= values that appear 2+ times in the same file
    Ignores:    files with no id= assignments; unique ids
    Basis:      RAW (regex-scans file_ctx.raw for id="..." patterns)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag duplicate Rule id values. Returns one Match per duplicate occurrence (after the first)."""
        if not file_ctx.raw:
            return []
        seen: dict[str, int] = {}
        matches: list[Match] = []
        for m in re.finditer(r'\bid\s*=\s*["\']([^"\']+)["\']', file_ctx.raw):
            rule_id = m.group(1)
            line = file_ctx.raw[:m.start()].count("\n") + 1
            count = seen.get(rule_id, 0)
            if count > 0:
                matches.append(Match(
                    file=file_ctx.path,
                    line=line,
                    matched_value=rule_id,
                ))
            seen[rule_id] = count + 1
        return matches
