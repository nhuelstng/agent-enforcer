"""Tests for pr_commenter module."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from scripts.pr_commenter import (
    RULE_MARKER_RE,
    SUMMARY_MARKER,
    existing_inline_keys,
    inline_body,
    post_comments,
    post_inline_comments,
    summary_body,
    upsert_summary,
)


def test_summary_body_zero_violations():
    violations = []
    body = summary_body(violations, sha="abc123")
    assert body.startswith(SUMMARY_MARKER)
    assert "No violations found" in body
    assert "abc123" in body


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


def test_summary_body_uses_injected_now():
    fixed = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
    body = summary_body([], sha="abc123", now=fixed)
    assert "2025-01-02 03:04 UTC" in body


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


def test_upsert_summary_edits_existing_with_leading_whitespace():
    existing = MagicMock()
    existing.body = "\n  <!-- enforcer-summary -->\nold body"
    existing.html_url = "https://github.com/owner/repo/issues/1#issuecomment-99"

    issue = MagicMock()
    issue.get_comments.return_value = [existing]

    repo = MagicMock()
    repo.get_issue.return_value = issue

    pr = MagicMock()
    pr.number = 1

    url = upsert_summary(repo, pr, [], sha="abc123")
    existing.edit.assert_called_once()
    assert url == "https://github.com/owner/repo/issues/1#issuecomment-99"


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


def test_post_inline_comments_continues_on_api_error():
    pr = MagicMock()
    pr.get_review_comments.return_value = []

    # First call raises, second succeeds.
    pr.create_review_comment.side_effect = [RuntimeError("api 403"), None]

    violations = [
        {"rule_id": "no-print", "file": "src/app.py", "line": 42,
         "severity": "error", "message": "m", "fix_instruction": "f"},
        {"rule_id": "no-docstring", "file": "src/util.py", "line": 7,
         "severity": "warn", "message": "missing", "fix_instruction": "add doc"},
    ]
    posted, skipped = post_inline_comments(pr, violations)
    assert posted == 1
    assert skipped == 1
    assert pr.create_review_comment.call_count == 2


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
