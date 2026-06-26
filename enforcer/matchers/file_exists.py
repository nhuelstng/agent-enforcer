from __future__ import annotations
import os
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class FileExistsMatcher:
    read_target: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        if self.read_target in shared_ctx:
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        full_path = os.path.join(self.workspace, self.read_target.replace("**/", ""))
        if os.path.exists(full_path):
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        return []
