from __future__ import annotations
import fnmatch
import re
from dataclasses import dataclass, field
from typing import Callable
from enforcer.types import Severity, Match, FileContext, LLMConsequence
from enforcer.matchers.allowlist import AllowlistMatcher
from enforcer.combinators.core import AllOf
from enforcer.predicates.combinators import All as AllPred

def _is_combinator(obj) -> bool:
    return (hasattr(obj, "matchers") or hasattr(obj, "matcher")) and hasattr(obj, "find")

def _run_matcher(matcher, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
    if isinstance(matcher, AllowlistMatcher):
        return matcher.find(file_ctx, shared_ctx)
    return matcher.find(file_ctx)

def _glob_match(path: str, pattern: str) -> bool:
    normalized = re.sub(r'^\*+/', '', pattern)
    if fnmatch.fnmatch(path, normalized):
        return True
    return fnmatch.fnmatch(path, pattern)

@dataclass
class Rule:
    id: str
    severity: Severity
    matchers: list
    file_globs: list[str]
    exclude_globs: list[str] = field(default_factory=list)
    workspace: str | None = None
    read_targets: list[str] = field(default_factory=list)
    predicates: list = field(default_factory=list)
    message: str | Callable = ""
    fix_instruction: str = ""
    llm_consequence: LLMConsequence | None = None

    def check(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        if self._excluded(file_ctx.path):
            return []

        if len(self.matchers) == 1 and _is_combinator(self.matchers[0]):
            all_matches = _run_matcher(self.matchers[0], file_ctx, shared_ctx)
        else:
            combined = AllOf(self.matchers)
            all_matches = combined.find(file_ctx, shared_ctx)

        for pred in self.predicates:
            all_matches = [m for m in all_matches if pred.test(m)]

        for m in all_matches:
            m.rule_id = self.id
            m.severity = self.severity
            m.fix_instruction = self.fix_instruction
            m.message = self._render_message(m)

        return all_matches

    def _excluded(self, path: str) -> bool:
        return any(_glob_match(path, pat) for pat in self.exclude_globs)

    def _render_message(self, match: Match) -> str:
        if callable(self.message):
            return self.message(match)
        out = self.message
        for key, val in [
            ("matched_value", match.matched_value),
            ("file", match.file),
            ("line", match.line),
            ("column", match.column),
        ]:
            out = out.replace("{" + key + "}", str(val))
        return out
