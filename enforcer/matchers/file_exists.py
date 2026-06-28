"""FileExistsMatcher: checks if a file matching a glob exists. Used with Not to enforce 'test file must exist'."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class FileExistsMatcher:
    """Checks if any file matching read_target glob exists. Emits no match if found; used with Not combinator to flag missing files."""
    read_target: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Emit a match if a file matching the read_target glob exists. Returns list of Match."""
        shared_ctx = shared_ctx or {}
        if self.read_target in shared_ctx:
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        # ponytail: pathlib.Path.glob handles ** and * patterns correctly
        root = Path(self.workspace)
        if any(root.glob(self.read_target)):
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        return []
