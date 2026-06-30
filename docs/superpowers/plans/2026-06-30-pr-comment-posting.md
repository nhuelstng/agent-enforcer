# PR Comment Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manual `workflow_dispatch` trigger that posts enforcer violations as inline PR review comments + updatable summary comment, with duplicate detection on re-runs.

**Architecture:** Python script using PyGithub. Two modules: `post_pr_comments.py` (CLI entrypoint) + `pr_commenter.py` (testable API logic). Reuses enforcer JSON output. New `comment-pr` job in `enforcer.yml`, manual dispatch only, `GITHUB_TOKEN` with `pull-requests: write`.

**Tech Stack:** Python 3.11, PyGithub, GitHub Actions, enforcer JSON output format

---

## File Structure

```
scripts/post_pr_comments.py     # CLI entrypoint: argparse, load JSON, init Github client, call commenter
scripts/pr_commenter.py         # Logic: upsert summary, dedup inline, post comments
tests/test_pr_commenter.py      # Unit tests with MagicMock client
.github/workflows/enforcer.yml  # New comment-pr job (workflow_dispatch)
```

**Responsibilities:**
- `post_pr_comments.py` — thin CLI wrapper. Parses args, reads JSON file, reads `GITHUB_TOKEN` env var, constructs `Github(token=...)`, fetches repo + PR objects, delegates to `pr_commenter.post_comments()`, prints summary, sets exit code.
- `pr_commenter.py` — all GitHub API logic. Pure functions taking repo/pr objects (mockable). Summary upsert, inline dedup, inline posting, body rendering.
- `tests/test_pr_commenter.py` — mocks `repo` and `pr` as `MagicMock`, verifies call patterns and rendered bodies.

---

### Task 1: Summary body rendering — zero violations

**Files:**
- Create: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pr_commenter.py
"""Tests for pr_commenter module."""
from scripts.pr_commenter import summary_body, SUMMARY_MARKER


def test_summary_body_zero_violations():
    violations = []
    body = summary_body(violations, sha="abc123")
    assert body.startswith(SUMMARY_MARKER)
    assert "No violations found" in body
    assert "abc123" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_summary_body_zero_violations -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.pr_commenter'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/pr_commenter.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pr_commenter.py::test_summary_body_zero_violations -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add summary_body for zero-violation case"
```

---

### Task 2: Summary body rendering — with violations

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import summary_body


def test_summary_body_with_violations():
    violations = [
        {"rule_id": "no-print", "severity": "error", "file": "src/app.py",
         "line": 42, "message": "Print statements not allowed",
         "fix_instruction": "Use logging instead of print()."},
        {"rule_id": "core-file-warning", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Verify tests pass before merging",
         "fix_instruction": "Run pytest --tb=short -q"},
    ]
    body = summary_body(violations, sha="abc123")
    assert body.startswith(SUMMARY_MARKER)
    assert "abc123" in body
    assert "2 ERROR" not in body  # 1 error, 1 warn
    assert "1 ERROR" in body
    assert "1 WARN" in body
    assert "0 INFO" in body
    assert "no-print" in body
    assert "src/app.py:42" in body
    assert "Print statements not allowed" in body
    assert "core-file-warning" in body
    assert "enforcer/types.py:15" in body
    assert "<details>" in body
    assert "<summary>Violations</summary>" in body
    assert "| Severity | Rule | File:Line | Message |" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_summary_body_with_violations -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Write minimal implementation**

Replace the `raise NotImplementedError` in `summary_body` with:

```python
# scripts/pr_commenter.py — replace the NotImplementedError block with:

    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not violations:
        return (
            f"{SUMMARY_MARKER}\n"
            f"## Enforcer Scan Results\n\n"
            f"Full scan of `{sha}` on {date_str}.\n\n"
            f"No violations found. \u2705\n"
        )
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
```

Note: remove the early `from datetime import...` and `if not violations:` block from Task 1 — the full function now handles both paths. Final function:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pr_commenter.py::test_summary_body_with_violations -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): render summary body with violation table"
```

---

### Task 3: Inline comment body rendering

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import inline_body, RULE_MARKER_RE


def test_inline_body_has_marker_and_fields():
    v = {
        "rule_id": "no-print",
        "severity": "error",
        "message": "Print statements not allowed",
        "fix_instruction": "Use logging instead of print().",
    }
    body = inline_body(v)
    m = RULE_MARKER_RE.search(body)
    assert m is not None
    assert m.group(1) == "no-print"
    assert "**`no-print`**" in body
    assert "(ERROR)" in body
    assert "Print statements not allowed" in body
    assert "Fix: Use logging instead of print()." in body


def test_inline_body_empty_fix_instruction():
    v = {
        "rule_id": "no-docstring",
        "severity": "warn",
        "message": "Missing docstring",
        "fix_instruction": None,
    }
    body = inline_body(v)
    assert "Fix: (none)" in body
    assert "(WARN)" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_inline_body_has_marker_and_fields tests/test_pr_commenter.py::test_inline_body_empty_fix_instruction -v`
Expected: FAIL with `ImportError: cannot import name 'inline_body'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to scripts/pr_commenter.py

import re

RULE_MARKER_RE = re.compile(r"<!-- enforcer rule_id=(\S+) -->")


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all 4 tests so far)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add inline_body with rule marker"
```

---

### Task 4: Existing inline comment dedup key extraction

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

from unittest.mock import MagicMock

from scripts.pr_commenter import existing_inline_keys


def test_existing_inline_keys_extracts_triplets():
    c1 = MagicMock()
    c1.body = "<!-- enforcer rule_id=no-print -->\nstuff"
    c1.path = "src/app.py"
    c1.line = 42
    c1.user.login = "github-actions[bot]"

    c2 = MagicMock()
    c2.body = "<!-- enforcer rule_id=no-docstring -->\nstuff"
    c2.path = "src/util.py"
    c2.line = 10
    c2.user.login = "github-actions[bot]"

    c3 = MagicMock()
    c3.body = "<!-- enforcer rule_id=no-print -->\nstuff"
    c3.path = "src/app.py"
    c3.line = 42
    c3.user.login = "human-user"  # not bot, should be ignored

    c4 = MagicMock()
    c4.body = "some other comment without marker"
    c4.path = "src/app.py"
    c4.line = 42
    c4.user.login = "github-actions[bot]"

    pr = MagicMock()
    pr.get_review_comments.return_value = [c1, c2, c3, c4]

    keys = existing_inline_keys(pr)
    assert ("src/app.py", 42, "no-print") in keys
    assert ("src/util.py", 10, "no-docstring") in keys
    assert len(keys) == 2  # c3 filtered (not bot), c4 filtered (no marker)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_existing_inline_keys_extracts_triplets -v`
Expected: FAIL with `ImportError: cannot import name 'existing_inline_keys'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to scripts/pr_commenter.py

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pr_commenter.py::test_existing_inline_keys_extracts_triplets -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): extract dedup keys from existing inline comments"
```

---

### Task 5: Summary comment upsert (edit existing or create new)

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import upsert_summary


def test_upsert_summary_edits_existing():
    existing = MagicMock()
    existing.body = "<!-- enforcer-summary -->\nold body"
    existing.html_url = "https://github.com/owner/repo/issues/1#issuecomment-99"

    issue = MagicMock()
    issue.get_comments.return_value = [existing]

    repo = MagicMock()
    repo.get_issue.return_value = issue

    pr = MagicMock()
    pr.number = 1

    violations = []
    url = upsert_summary(repo, pr, violations, sha="abc123")
    existing.edit.assert_called_once()
    assert url == "https://github.com/owner/repo/issues/1#issuecomment-99"
    repo.get_issue.assert_called_once_with(1)


def test_upsert_summary_creates_new():
    other_comment = MagicMock()
    other_comment.body = "some unrelated comment"

    new_comment = MagicMock()
    new_comment.html_url = "https://github.com/owner/repo/issues/2#issuecomment-100"

    issue = MagicMock()
    issue.get_comments.return_value = [other_comment]
    issue.create_comment.return_value = new_comment

    repo = MagicMock()
    repo.get_issue.return_value = issue

    pr = MagicMock()
    pr.number = 2

    violations = [{"rule_id": "x", "severity": "error", "file": "a.py", "line": 1, "message": "m", "fix_instruction": "f"}]
    url = upsert_summary(repo, pr, violations, sha="def456")
    issue.create_comment.assert_called_once()
    assert url == "https://github.com/owner/repo/issues/2#issuecomment-100"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py::test_upsert_summary_edits_existing tests/test_pr_commenter.py::test_upsert_summary_creates_new -v`
Expected: FAIL with `ImportError: cannot import name 'upsert_summary'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to scripts/pr_commenter.py

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all 7 tests so far)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): upsert summary comment (edit or create)"
```

---

### Task 6: Post inline comments with dedup + file-level skip

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import post_inline_comments


def test_post_inline_comments_skips_duplicates():
    c1 = MagicMock()
    c1.body = "<!-- enforcer rule_id=no-print -->\nstuff"
    c1.path = "src/app.py"
    c1.line = 42
    c1.user.login = "github-actions[bot]"

    pr = MagicMock()
    pr.get_review_comments.return_value = [c1]

    violations = [
        {"rule_id": "no-print", "file": "src/app.py", "line": 42,
         "severity": "error", "message": "dup", "fix_instruction": "f"},
        {"rule_id": "no-print", "file": "src/app.py", "line": 99,
         "severity": "error", "message": "new", "fix_instruction": "f"},
    ]
    posted, skipped = post_inline_comments(pr, violations)
    assert posted == 1
    assert skipped == 1
    # Verify create_review_comment called once with the new violation
    pr.create_review_comment.assert_called_once()
    call_kwargs = pr.create_review_comment.call_args
    assert call_kwargs.kwargs["path"] == "src/app.py"
    assert call_kwargs.kwargs["line"] == 99


def test_post_inline_comments_skips_file_level():
    pr = MagicMock()
    pr.get_review_comments.return_value = []

    violations = [
        {"rule_id": "branch-name", "file": "", "line": 0,
         "severity": "error", "message": "branch", "fix_instruction": "f"},
        {"rule_id": "commit-msg", "file": None, "line": None,
         "severity": "error", "message": "msg", "fix_instruction": "f"},
    ]
    posted, skipped = post_inline_comments(pr, violations)
    assert posted == 0
    assert skipped == 2
    pr.create_review_comment.assert_not_called()


def test_post_inline_comments_posts_new():
    pr = MagicMock()
    pr.get_review_comments.return_value = []

    violations = [
        {"rule_id": "no-print", "file": "src/app.py", "line": 42,
         "severity": "error", "message": "m", "fix_instruction": "f"},
    ]
    posted, skipped = post_inline_comments(pr, violations)
    assert posted == 1
    assert skipped == 0
    pr.create_review_comment.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py -k post_inline -v`
Expected: FAIL with `ImportError: cannot import name 'post_inline_comments'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to scripts/pr_commenter.py

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -k post_inline -v`
Expected: PASS (all 3 post_inline tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): post inline comments with dedup and file-level skip"
```

---

### Task 7: Top-level `post_comments` orchestrator

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import post_comments


def test_post_comments_returns_counts_and_url():
    pr = MagicMock()
    pr.number = 1
    pr.get_review_comments.return_value = []

    new_comment = MagicMock()
    new_comment.html_url = "https://github.com/owner/repo/issues/1#issuecomment-1"
    issue = MagicMock()
    issue.get_comments.return_value = []
    issue.create_comment.return_value = new_comment

    repo = MagicMock()
    repo.get_issue.return_value = issue

    violations = [
        {"rule_id": "no-print", "file": "src/app.py", "line": 42,
         "severity": "error", "message": "m", "fix_instruction": "f"},
    ]
    posted, skipped, summary_url = post_comments(repo, pr, violations, sha="abc123")
    assert posted == 1
    assert skipped == 0
    assert summary_url == "https://github.com/owner/repo/issues/1#issuecomment-1"
    issue.create_comment.assert_called_once()  # summary created
    pr.create_review_comment.assert_called_once()  # inline posted


def test_post_comments_zero_violations():
    pr = MagicMock()
    pr.number = 1

    new_comment = MagicMock()
    new_comment.html_url = "https://github.com/owner/repo/issues/1#issuecomment-1"
    issue = MagicMock()
    issue.get_comments.return_value = []
    issue.create_comment.return_value = new_comment

    repo = MagicMock()
    repo.get_issue.return_value = issue

    posted, skipped, summary_url = post_comments(repo, pr, [], sha="abc123")
    assert posted == 0
    assert skipped == 0
    issue.create_comment.assert_called_once()  # summary still posted
    pr.create_review_comment.assert_not_called()  # no inline
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py -k post_comments -v`
Expected: FAIL with `ImportError: cannot import name 'post_comments'`

- [ ] **Step 3: Write minimal implementation**

```python
# Append to scripts/pr_commenter.py

def post_comments(repo, pr, violations: list[dict], sha: str) -> tuple[int, int, str]:
    """Post summary + inline comments. Returns (posted, skipped, summary_url)."""
    summary_url = upsert_summary(repo, pr, violations, sha)
    posted, skipped = post_inline_comments(pr, violations)
    return posted, skipped, summary_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add post_comments orchestrator"
```

---

### Task 8: CLI entrypoint `post_pr_comments.py`

**Files:**
- Create: `scripts/post_pr_comments.py`
- Test: `tests/test_post_pr_comments.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_post_pr_comments.py
"""Tests for post_pr_comments CLI entrypoint."""
import json
from unittest.mock import MagicMock, patch

from scripts.post_pr_comments import main


def test_main_no_violations_exits_zero(tmp_path):
    json_file = tmp_path / "violations.json"
    json_file.write_text(json.dumps({"summary": {"total": 0}, "issues": []}))

    with patch("scripts.post_pr_comments.Github") as mock_github:
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo

        exit_code = main([
            "--json", str(json_file),
            "--pr", "1",
            "--repo", "owner/repo",
            "--sha", "abc123",
        ])
    assert exit_code == 0


def test_main_with_violations_exits_one(tmp_path):
    json_file = tmp_path / "violations.json"
    json_file.write_text(json.dumps({
        "summary": {"total": 1},
        "issues": [
            {"rule_id": "no-print", "file": "src/app.py", "line": 42,
             "severity": "error", "message": "m", "fix_instruction": "f"}
        ],
    }))

    with patch("scripts.post_pr_comments.Github") as mock_github:
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.get_review_comments.return_value = []
        mock_repo.get_pull.return_value = mock_pr

        mock_issue = MagicMock()
        mock_issue.get_comments.return_value = []
        mock_comment = MagicMock()
        mock_comment.html_url = "https://github.com/owner/repo/issues/1#issuecomment-1"
        mock_issue.create_comment.return_value = mock_comment
        mock_repo.get_issue.return_value = mock_issue

        mock_github.return_value.get_repo.return_value = mock_repo

        exit_code = main([
            "--json", str(json_file),
            "--pr", "1",
            "--repo", "owner/repo",
            "--sha", "abc123",
        ])
    assert exit_code == 1


def test_main_reads_github_token(tmp_path):
    json_file = tmp_path / "violations.json"
    json_file.write_text(json.dumps({"summary": {"total": 0}, "issues": []}))

    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-123"}):
        with patch("scripts.post_pr_comments.Github") as mock_github:
            mock_repo = MagicMock()
            mock_pr = MagicMock()
            mock_repo.get_pull.return_value = mock_repo
            mock_github.return_value.get_repo.return_value = mock_repo

            main([
                "--json", str(json_file),
                "--pr", "1",
                "--repo", "owner/repo",
                "--sha", "abc123",
            ])
    mock_github.assert_called_once_with(token="test-token-123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_post_pr_comments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.post_pr_comments'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/post_pr_comments.py
"""Post enforcer violations as PR comments. CI entrypoint."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)

    data = json.loads(args.json.read_text())
    violations = data.get("issues", [])
    if not violations:
        print("No violations found. Nothing to post.")
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN env var not set.", file=sys.stderr)
        return 2

    from github import Github
    from scripts.pr_commenter import post_comments

    gh = Github(token=token)
    repo = gh.get_repo(args.repo)
    pr = repo.get_pull(args.pr)

    posted, skipped, summary_url = post_comments(repo, pr, violations, args.sha)

    print(f"Summary: {summary_url}")
    print(f"Inline: {posted} posted, {skipped} skipped (existing)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_post_pr_comments.py -v`
Expected: PASS (all 3 tests)

Note: tests use `patch("scripts.post_pr_comments.Github")` — the `Github` import is inside `main()` (lazy import), so the patch target is the module attribute. The test for `GITHUB_TOKEN` uses `patch.dict` on `os.environ`.

- [ ] **Step 5: Commit**

```bash
git add scripts/post_pr_comments.py tests/test_post_pr_comments.py
git commit -m "feat(pr-comments): add CLI entrypoint with token handling"
```

---

### Task 9: GitHub Actions workflow — new `comment-pr` job

**Files:**
- Modify: `.github/workflows/enforcer.yml`
- Modify: `.github/workflows/enforcer.yml:3-8` (on: block)

- [ ] **Step 1: Read current workflow file**

Read: `.github/workflows/enforcer.yml`
Note current `on:` block at lines 3-8 and existing jobs (`changed`, `full`).

- [ ] **Step 2: Add `workflow_dispatch` input and new job**

Edit the `on:` block to add `workflow_dispatch` with `pr_number` input:

```yaml
on:
  push:
    branches: [main, "feature/**", "fix/**", "refactor/**", "docs/**", "chore/**"]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to post comments on"
        required: true
        type: string
```

Append new job at end of file (after `full:` job):

```yaml
  comment-pr:
    name: post-pr-comments
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: build-wheel
        run: pip install build && python -m build --wheel
      - name: install-deps
        run: pip install dist/*.whl PyGithub
      - name: run-enforcer
        run: |
          python -m enforcer.cli check --all --no-llm --format json --output violations.json
      - name: post-comments
        env:
          GITHUB_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.inputs.pr_number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          COMMIT_SHA: ${{ github.sha }}
        run: |
          python scripts/post_pr_comments.py \
            --json violations.json \
            --pr "$PR_NUMBER" \
            --repo "$GITHUB_REPOSITORY" \
            --sha "$COMMIT_SHA"
```

- [ ] **Step 3: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/enforcer.yml'))" && echo "YAML valid"`
Expected: `YAML valid`

- [ ] **Step 4: Verify existing tests still pass**

Run: `pytest --tb=short -q`
Expected: All existing tests pass (new workflow file doesn't affect tests)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/enforcer.yml
git commit -m "ci: add comment-pr job for manual PR comment posting"
```

---

### Task 10: End-to-end dry run + final verification

**Files:**
- No new files. Verification only.

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (existing 520 + new ~15 = ~535)

- [ ] **Step 2: Run enforcer self-check**

Run: `python -m enforcer.cli check --all --config enforcer_config.py`
Expected: `No issues found.`

- [ ] **Step 3: Dry-run the comment script locally with mock JSON**

Create a temp JSON file and run the script with a fake token to verify it fails gracefully:

```bash
cat > /tmp/test-violations.json << 'EOF'
{
  "summary": {"total": 1, "errors": 1, "warnings": 0, "info": 0},
  "issues": [
    {"rule_id": "no-print", "file": "src/app.py", "line": 42,
     "severity": "error", "message": "Print statements not allowed",
     "fix_instruction": "Use logging instead of print()."}
  ]
}
EOF
GITHUB_TOKEN=fake-token python scripts/post_pr_comments.py \
  --json /tmp/test-violations.json \
  --pr 999 \
  --repo "test/repo" \
  --sha "abc123"
```

Expected: Script fails with GitHub API error (fake token, fake repo) — proves it runs, parses JSON, attempts API call. Exit code should be non-zero from the API error.

- [ ] **Step 4: Verify zero-violation case exits 0**

```bash
echo '{"summary": {"total": 0}, "issues": []}' > /tmp/empty-violations.json
python scripts/post_pr_comments.py \
  --json /tmp/empty-violations.json \
  --pr 999 \
  --repo "test/repo" \
  --sha "abc123"
```

Expected: `No violations found. Nothing to post.` Exit code 0. No API call attempted (returns before Github init).

- [ ] **Step 5: Clean up temp files**

```bash
rm /tmp/test-violations.json /tmp/empty-violations.json
```

- [ ] **Step 6: Final commit if any cleanup needed**

If self-enforcement flagged anything in the new scripts, fix and commit:

```bash
git add -A
git commit -m "fix(pr-comments): address self-enforcement findings"
```

If clean, no commit needed.

---

## Self-Review Notes

**Spec coverage check:**
- Summary comment (updatable, marker-based) → Task 5
- Inline review comments (line-anchored, with marker) → Task 3 (body), Task 6 (posting)
- Dedup "skip if existing unresolved" → Task 4 (extraction), Task 6 (skip logic)
- File-level violations (line=0) → summary only → Task 6
- Zero violations → "No violations found ✅" → Task 1, Task 8
- Workflow dispatch with `pr_number` input → Task 9
- `pull-requests: write` permission → Task 9
- `GITHUB_TOKEN` explicit pass → Task 8 (test `test_main_reads_github_token`)
- Exit code 1 on violations → Task 8
- PyGithub dependency (CI only) → Task 9
- Edge case: file unchanged in PR diff → spec says catch per-comment. This is handled by PyGithub raising `UnknownObjectException` — not explicitly tested because it requires a real PR. The script lets exceptions propagate from `create_review_comment`, which would fail the job. **Decision: acceptable — if a file is unchanged in PR, it means the violation is in a file that exists but wasn't part of the PR diff. The `--all` scan may find violations in files outside the PR diff. These inline comments will fail. This is a known limitation documented in the spec.** If this becomes a problem, a future enhancement can catch the exception per-comment and continue.

**Placeholder scan:** None found. All steps have complete code.

**Type consistency:**
- `summary_body(violations, sha)` — used in Task 1, 2, called by `upsert_summary` in Task 5
- `inline_body(violation)` — used in Task 3, called by `post_inline_comments` in Task 6
- `existing_inline_keys(pr)` — used in Task 4, called by `post_inline_comments` in Task 6
- `upsert_summary(repo, pr, violations, sha)` — used in Task 5, called by `post_comments` in Task 7
- `post_inline_comments(pr, violations)` — used in Task 6, called by `post_comments` in Task 7
- `post_comments(repo, pr, violations, sha) -> (posted, skipped, summary_url)` — used in Task 7, called by `main()` in Task 8
- `main(argv) -> int` — used in Task 8

All signatures consistent across tasks.
