"""PairedFileMatcher: cross-file paired file existence. Source file staged -> derived file must exist."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs


@dataclass
class PairedFileMatcher:
    """Given a source file, checks if a derived (paired) file exists.
    Uses {stem} (filename without extension) and {dir} (parent directory name) in derived_glob.
    Emits a match if the paired file does NOT exist."""
    source_glob: str
    derived_glob: str
    workspace: str = "."
    exclude_stems: list[str] = field(default_factory=lambda: ["__init__"])
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        path = file_ctx.path
        stem = Path(path).stem

        if stem in self.exclude_stems:
            return []

        # ponytail: skip derived files themselves (spec/test) to avoid recursive pairing
        if ".spec." in path or ".test." in path or path.startswith("test_") or "/tests/" in path or path.startswith("tests/"):
            return []

        # ponytail: skip if the source path doesn't match the source_glob
        from enforcer.rule import _glob_match
        if not _glob_match(path, self.source_glob):
            return []

        # Build the derived path by substituting {stem} and {dir}
        parent_dir = Path(path).parent.name
        derived_path = self.derived_glob.replace("{stem}", stem).replace("{dir}", parent_dir)

        full_path = os.path.join(self.workspace, derived_path)
        if os.path.exists(full_path):
            return []

        return [Match(
            file=file_ctx.path,
            line=0,
            matched_value=f"missing {derived_path}",
        )]
