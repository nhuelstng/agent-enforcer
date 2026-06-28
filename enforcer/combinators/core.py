"""Combinator implementations: compose matchers with AND/OR/NOT logic."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext

def _run(matcher, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
    if shared_ctx is None:
        shared_ctx = {}
    return matcher.find(file_ctx, shared_ctx)

@dataclass
class AllOf:
    """All matchers must find at least one match. Returns combined matches if all succeed."""
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Return combined matches if all matchers find at least one match, else empty. Returns list of Match."""
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if all(r for r in results):
            return [m for r in results for m in r]
        return []

@dataclass
class AnyOf:
    """At least one matcher must find a match. Returns combined matches from all that matched."""
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Return combined matches if any matcher finds a match, else empty. Returns list of Match."""
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return [m for r in results if r for m in r]
        return []

@dataclass
class OneOf:
    """Exactly one matcher must find a match. Fails if zero or more than one match."""
    matchers: list

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Return matches if exactly one matcher finds a match, else empty. Returns list of Match."""
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        non_empty = [r for r in results if r]
        if len(non_empty) == 1:
            return non_empty[0]
        return []

@dataclass
class Not:
    """Negation: emits a synthetic match if the inner matcher finds NOTHING. Used to enforce 'file must exist', 'pattern must be absent'."""
    matcher: object
    message_on_absence: str = "Expected pattern not found."

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Emit synthetic match if inner matcher finds nothing, else empty. Returns list of Match."""
        results = _run(self.matcher, file_ctx, shared_ctx)
        if results:
            return []
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(absent)",
            message=self.message_on_absence,
        )]

@dataclass
class NoneOf:
    """No matcher may find a match. Emits a synthetic match if any matcher finds something."""
    matchers: list
    message_on_absence: str = "All forbidden patterns absent."

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Emit synthetic match if no matcher finds a match, else empty. Returns list of Match."""
        results = [_run(m, file_ctx, shared_ctx) for m in self.matchers]
        if any(r for r in results):
            return []
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value="(all absent)",
            message=self.message_on_absence,
        )]
