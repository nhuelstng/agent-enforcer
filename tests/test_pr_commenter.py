"""Tests for pr_commenter module."""
from scripts.pr_commenter import summary_body, SUMMARY_MARKER


def test_summary_body_zero_violations():
    violations = []
    body = summary_body(violations, sha="abc123")
    assert body.startswith(SUMMARY_MARKER)
    assert "No violations found" in body
    assert "abc123" in body
