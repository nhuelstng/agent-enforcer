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
        basename = os.path.basename(self.read_target.replace("**/", "").replace("*", ""))
        target_ctx = shared_ctx.get(basename) or shared_ctx.get(os.path.basename(self.read_target))
        if not target_ctx:
            return []
        if not file_ctx.raw or not target_ctx.raw:
            return []
        allowed = self.extractor(target_ctx.raw)
        used = self.consumer(file_ctx.raw)
        undefined = used - allowed
        return [
            Match(file=file_ctx.path, line=0, matched_value=item)
            for item in undefined
        ]
