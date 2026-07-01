"""Shared glob matching: supports ** recursive globs (fnmatch does not handle **).

** matches zero or more path segments — 'dir/**/x' matches both 'dir/x' and 'dir/a/b/x'.
"""
from __future__ import annotations
import fnmatch
import re


def glob_match(path: str, pattern: str) -> bool:
    """Match path against glob pattern, supporting ** recursive globs."""
    candidates = {pattern}
    candidates.add(re.sub(r"/\*\*", "", pattern))   # dir/**/x -> dir/x      (zero segments)
    candidates.add(re.sub(r"\*\*/", "", pattern))    # **/x -> x             (leading zero segments)
    candidates.add(pattern.replace("**", "*"))       # ** -> *               (single-seg wildcard)
    for c in candidates:
        if fnmatch.fnmatch(path, c):
            return True
    return False
