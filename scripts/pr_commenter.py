"""Post enforcer violations to GitHub PR as comments. Testable logic module."""
from __future__ import annotations

SUMMARY_MARKER = "<!-- enforcer-summary -->"


def summary_body(violations: list[dict], sha: str) -> str:
    """Render the summary comment body for a list of violations."""
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not violations:
        return (
            f"{SUMMARY_MARKER}\n"
            f"## Enforcer Scan Results\n\n"
            f"Full scan of `{sha}` on {date_str}.\n\n"
            f"No violations found. \u2705\n"
        )
    # Non-empty case implemented in Task 2
    raise NotImplementedError
