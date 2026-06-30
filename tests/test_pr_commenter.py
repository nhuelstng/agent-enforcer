"""Tests for pr_commenter module."""
from scripts.pr_commenter import summary_body, SUMMARY_MARKER


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
