"""enforcerignore loading: reads .enforcerignore from workspace root, applies as exclude patterns."""
from __future__ import annotations
import os
from pathlib import Path


def load_enforcerignore(workspace: str = ".") -> list[str]:
    """Load .enforcerignore from workspace root. Returns list of glob patterns.
    Returns empty list if file doesn't exist."""
    ignore_path = Path(workspace, ".enforcerignore")
    if not ignore_path.exists():
        return []
    try:
        content = ignore_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    patterns = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def is_ignored(path: str, patterns: list[str]) -> bool:
    """Check if a path matches any .enforcerignore pattern."""
    if not patterns:
        return False
    import fnmatch
    basename = os.path.basename(path)
    parts = path.split(os.sep)
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(basename, pat):
            return True
        # Handle ** patterns via simple substring check for directory exclusions
        if pat.endswith("/") and pat[:-1] in parts:
            return True
        # Match against any path segment (covers dir names without trailing /)
        if any(fnmatch.fnmatch(seg, pat.rstrip("/")) for seg in parts):
            return True
    return False
