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


def existing_inline_keys(pr) -> set[tuple[str, int, str]]:
    """Extract (path, line, rule_id) keys from existing bot review comments."""
    keys = set()
    for c in pr.get_review_comments():
        if c.user.login != "github-actions[bot]":
            continue
        m = RULE_MARKER_RE.search(c.body)
        if m:
            keys.add((c.path, c.line, m.group(1)))
    return keys


def upsert_summary(repo, pr, violations: list[dict], sha: str) -> str:
    """Find existing summary comment by marker and edit, or create new. Returns comment URL."""
    body = summary_body(violations, sha)
    issue = repo.get_issue(pr.number)
    for comment in issue.get_comments():
        if comment.body.startswith(SUMMARY_MARKER):
            comment.edit(body)
            return comment.html_url
    comment = issue.create_comment(body)
    return comment.html_url


def post_inline_comments(pr, violations: list[dict]) -> tuple[int, int]:
    """Post inline review comments, skipping duplicates and file-level violations.
    Returns (posted, skipped)."""
    existing = existing_inline_keys(pr)
    posted = 0
    skipped = 0
    for v in violations:
        file = v.get("file")
        line = v.get("line")
        rule_id = v.get("rule_id", "")
        if not file or not line:
            skipped += 1
            continue
        if (file, line, rule_id) in existing:
            skipped += 1
            continue
        body = inline_body(v)
        pr.create_review_comment(
            body=body,
            path=file,
            line=line,
        )
        posted += 1
    return posted, skipped


def post_comments(repo, pr, violations: list[dict], sha: str) -> tuple[int, int, str]:
    """Post summary + inline comments. Returns (posted, skipped, summary_url)."""
    summary_url = upsert_summary(repo, pr, violations, sha)
    posted, skipped = post_inline_comments(pr, violations)
    return posted, skipped, summary_url
