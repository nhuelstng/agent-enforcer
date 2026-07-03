"""enforcerignore loading: reads .enforcerignore from workspace root, applies as exclude patterns."""
from __future__ import annotations
import os
import re
import fnmatch
from pathlib import Path


def load_enforcerignore(workspace: str = ".") -> list[str]:
    """Load .enforcerignore from workspace root. Returns list of patterns.
    Returns empty list if file doesn't exist. Supports # comments and blank lines."""
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
    """Check if a path matches any .enforcerignore pattern.
    Supports: glob patterns (*, ?, [chars]), ** recursive globs,
    directory patterns (trailing /), negation (!), root-relative (/)."""
    if not patterns:
        return False

    # ponytail: normalize to forward slashes — git emits /, Windows uses \
    normalized = path.replace(os.sep, "/")
    basename = os.path.basename(normalized)
    parts = [p for p in normalized.split("/") if p]

    ignored = False
    for pat in patterns:
        is_negation = pat.startswith("!")
        match_pat = pat[1:] if is_negation else pat
        if _match_pattern(normalized, basename, parts, match_pat):
            ignored = not is_negation

    return ignored


def _match_pattern(path: str, basename: str, parts: list[str], pat: str) -> bool:
    """Match a single pattern (without negation prefix) against a path."""
    # Root-relative: /foo means only at workspace root
    if pat.startswith("/"):
        pat = pat[1:]
        return fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(parts[0] if parts else "", pat)

    # Directory pattern: foo/ means match directory named foo anywhere in path
    if pat.endswith("/"):
        dir_name = pat[:-1]
        return any(fnmatch.fnmatch(seg, dir_name) for seg in parts)

    # ** recursive glob: **/foo or dir/**/foo
    if "**" in pat:
        return _match_recursive_glob(path, pat)

    # Basename match or full path match
    if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(basename, pat):
        return True

    # Match against any path segment
    return any(fnmatch.fnmatch(seg, pat) for seg in parts)


def _match_recursive_glob(path: str, pat: str) -> bool:
    """Match ** recursive glob patterns by expanding to candidate forms."""
    candidates = {pat}
    candidates.add(re.sub(r"/\*\*", "", pat))
    candidates.add(re.sub(r"\*\*/", "", pat))
    candidates.add(pat.replace("**", "*"))
    return any(fnmatch.fnmatch(path, c) for c in candidates)
