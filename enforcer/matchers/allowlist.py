from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Callable
from enforcer.types import Match, FileContext, Needs

@dataclass
class AllowlistMatcher:
    extractor: Callable[[str], set[str]]
    consumer: Callable[[str], set[str]]
    read_target: str
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        target_ctx = shared_ctx.get(self.read_target)
        if not target_ctx:
            for key, ctx in shared_ctx.items():
                if key.endswith(self.read_target.replace("**/", "").replace("*", "")):
                    target_ctx = ctx
                    break
        if not target_ctx:
            return []
        if file_ctx.raw is None or target_ctx.raw is None:
            return []
        allowed = self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        undefined = used - allowed
        return [
            Match(file=file_ctx.path, line=0, matched_value=item)
            for item in undefined
        ]
