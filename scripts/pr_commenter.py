"""Post enforcer violations to GitHub PR as comments. Testable logic module."""
from __future__ import annotations

import re

SUMMARY_MARKER = "<!-- enforcer-summary -->"
RULE_MARKER_RE = re.compile(r"<!-- enforcer rule_id=(\S+) -->")


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
    # Non-empty case
    counts = {"error": 0, "warn": 0, "info": 0}
    for v in violations:
        sev = v.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1
    rows = []
    for v in violations:
        sev = v.get("severity", "info").upper()
        rule = v.get("rule_id", "?")
        file = v.get("file", "?")
        line = v.get("line", 0)
        msg = v.get("message", "")
        rows.append(f"| {sev} | `{rule}` | `{file}:{line}` | {msg} |")
    table = "\n".join(rows)
    return (
        f"{SUMMARY_MARKER}\n"
        f"## Enforcer Scan Results\n\n"
        f"Full scan of `{sha}` on {date_str}.\n\n"
        f"**{counts['error']} ERROR** \u00b7 **{counts['warn']} WARN** \u00b7 **{counts['info']} INFO**\n\n"
        f"<details>\n"
        f"<summary>Violations</summary>\n\n"
        f"| Severity | Rule | File:Line | Message |\n"
        f"|----------|------|-----------|---------|\n"
        f"{table}\n\n"
        f"</details>\n\n"
        f"Inline comments posted for each anchorable violation. Re-run to refresh.\n"
    )


def inline_body(violation: dict) -> str:
    """Render an inline review comment body for a single violation."""
    rule_id = violation.get("rule_id", "?")
    severity = violation.get("severity", "info").upper()
    message = violation.get("message", "")
    fix = violation.get("fix_instruction") or "(none)"
    return (
        f"<!-- enforcer rule_id={rule_id} -->\n"
        f"**`{rule_id}`** ({severity})\n\n"
        f"{message}\n\n"
        f"Fix: {fix}"
    )
