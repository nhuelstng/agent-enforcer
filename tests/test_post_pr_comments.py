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
    mock_github.assert_not_called()


def test_main_with_violations_exits_one(tmp_path):
    json_file = tmp_path / "violations.json"
    json_file.write_text(json.dumps({
        "summary": {"total": 1},
        "issues": [
            {"rule_id": "no-print", "file": "src/app.py", "line": 42,
             "severity": "error", "message": "m", "fix_instruction": "f"}
        ],
    }))

    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-123"}):
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
    json_file.write_text(json.dumps({
        "summary": {"total": 1},
        "issues": [
            {"rule_id": "no-print", "file": "src/app.py", "line": 42,
             "severity": "error", "message": "m", "fix_instruction": "f"}
        ],
    }))

    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-123"}):
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

            main([
                "--json", str(json_file),
                "--pr", "1",
                "--repo", "owner/repo",
                "--sha", "abc123",
            ])
    mock_github.assert_called_once_with(login_or_token="test-token-123")
