"""Auto-fix infrastructure: apply_fixes groups matches by file and applies fix functions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from enforcer.types import Match, FileContext


@dataclass
class FixResult:
    """Result of applying fixes to one file."""
    path: str
    fixes_applied: int
    new_content: str


def _apply_fixes_for_file(file_path: str, file_matches: list[Match], workspace: str,
                          fix_providers: dict[str, Callable[[FileContext, Match], str]]) -> FixResult | None:
    """Apply all fixes for one file. Returns FixResult if any applied, else None."""
    full_path = Path(workspace, file_path)
    if not full_path.exists():
        return None
    raw = full_path.read_text(encoding="utf-8", errors="replace")
    ctx = FileContext(path=file_path, raw=raw)
    content = raw
    applied = 0
    for m in file_matches:
        fn = fix_providers.get(m.rule_id)
        if not fn:
            continue
        new_content = fn(ctx, m)
        if new_content != content:
            content = new_content
            ctx.raw = content
            m.fix_applied = "applied"
            applied += 1
    if applied == 0:
        return None
    full_path.write_text(content, encoding="utf-8")
    return FixResult(path=file_path, fixes_applied=applied, new_content=content)


def apply_fixes(
    matches: list[Match],
    workspace: str,
    fix_providers: dict[str, Callable[[FileContext, Match], str]],
) -> list[FixResult]:
    """Group matches by file, apply fix functions, write results.

    fix_providers maps rule_id to a fix function (FileContext, Match) -> str (new content).
    Returns one FixResult per file that had fixes applied.
    """
    by_file: dict[str, list[Match]] = {}
    for m in matches:
        if m.rule_id in fix_providers:
            by_file.setdefault(m.file, []).append(m)

    results: list[FixResult] = []
    for file_path, file_matches in by_file.items():
        result = _apply_fixes_for_file(file_path, file_matches, workspace, fix_providers)
        if result:
            results.append(result)
    return results
