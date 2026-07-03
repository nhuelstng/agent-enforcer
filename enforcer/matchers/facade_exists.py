"""FacadeExistsMatcher: flags directories matching source_glob that lack a facade file."""
from __future__ import annotations
import os
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.glob_util import glob_match


@dataclass
class FacadeExistsMatcher:
    """Flags directories matching source_glob that are missing the facade file.

    What:       flags files matching source_glob whose parent dir lacks {facade}
    Ignores:    files not matching source_glob; dirs with facade present
    Basis:      RAW (pathlib.Path checks on workspace)
    shared_ctx: none
    """
    source_glob: str
    facade: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag if file matches source_glob and its parent dir lacks facade. Returns list of Match."""
        if not glob_match(file_ctx.path, self.source_glob):
            return []
        parent = os.path.dirname(file_ctx.path)
        facade_path = os.path.join(self.workspace, parent, self.facade) if parent else os.path.join(self.workspace, self.facade)
        if os.path.isfile(facade_path):
            return []
        loc = f"{parent}/{self.facade}" if parent else self.facade
        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=f"{loc} missing",
        )]
