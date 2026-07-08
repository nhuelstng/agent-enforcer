"""PairedFileMatcher: cross-file paired file existence. Source file staged -> derived file must exist."""
from __future__ import annotations
import glob
import os
from pathlib import Path
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.glob_util import glob_match


@dataclass
class PairedFileMatcher:
    """Given a source file, checks if a derived (paired) file exists.
    Uses {stem} (filename without extension) and {dir} (parent directory name) in derived_glob.
    Supports glob wildcards (*, ?, **) in derived_glob — matches if at least one file matches.
    `**` matches across directory levels (recursive), so a co-located pair nested any
    depth below a fixed prefix (e.g. `frontend/src/app/**/{stem}.spec.ts`) is found.
    Emits a match if the paired file does NOT exist.

    Set `statuses` to restrict firing to specific git statuses (e.g. {"added"} to
    require a test only for newly-created files, not edits to pre-existing ones).
    Left as None, it fires regardless of status.

    What:       flags source files (matching source_glob, and — if set — with a git status in `statuses`) whose derived paired file does NOT exist on disk
    Ignores:    excluded stems (default __init__); spec/test files themselves; paths not matching source_glob; files whose status is not in `statuses`; pairs that exist
    Basis:      RAW (path stem/dir substitution + glob.glob on disk)
    shared_ctx: none (defensive default only)
    """
    source_glob: str
    derived_glob: str
    workspace: str = "."
    exclude_stems: list[str] = field(default_factory=lambda: ["__init__"])
    statuses: set[str] | None = None
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag source files whose derived paired file does not exist. Returns list of Match."""
        path = file_ctx.path
        stem = Path(path).stem

        if stem in self.exclude_stems:
            return []

        # ponytail: restrict to given git statuses when set (e.g. new files only)
        if self.statuses is not None and file_ctx.status not in self.statuses:
            return []

        # ponytail: skip derived files themselves (spec/test) to avoid recursive pairing
        if ".spec." in path or ".test." in path or path.startswith("test_") or "/tests/" in path or path.startswith("tests/"):
            return []

        # ponytail: skip if the source path doesn't match the source_glob
        if not glob_match(path, self.source_glob):
            return []

        # Build the derived path by substituting {stem} and {dir}
        parent_dir = Path(path).parent.name
        derived_path = self.derived_glob.replace("{stem}", stem).replace("{dir}", parent_dir)

        full_path = os.path.join(self.workspace, derived_path)
        # ponytail: recursive=True so `**` spans directory levels; harmless for exact
        # paths and single-`*` patterns. Without it, `**` collapses to a single `*`
        # (one level) and a co-located pair nested deeper is missed → false positive.
        if glob.glob(full_path, recursive=True):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=f"missing {derived_path}",
        )]
