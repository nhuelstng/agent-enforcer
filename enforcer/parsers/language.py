"""Language detection: maps file extensions to Needs (AST_TS, AST_PY, AST_CSS)."""
from __future__ import annotations
import os
from enforcer.types import Needs

_EXT_TO_NEEDS = {
    ".ts": Needs.AST_TS,
    ".tsx": Needs.AST_TS,
    ".js": Needs.AST_TS,
    ".jsx": Needs.AST_TS,
    ".py": Needs.AST_PY,
    ".scss": Needs.AST_CSS,
    ".css": Needs.AST_CSS,
}

def language_for_path(path: str) -> Needs | None:
    """Return the Needs (AST kind) for a file path based on its extension."""
    ext = os.path.splitext(path)[1]
    return _EXT_TO_NEEDS.get(ext)
