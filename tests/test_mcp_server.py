import json
from enforcer.mcp_server import check_conventions, list_conventions, verify_fix


def test_list_conventions_returns_markdown():
    md = list_conventions()
    assert "# Conventions" in md


def test_verify_fix_returns_pass_or_fail():
    result = json.loads(verify_fix(path="README.md", rule_id="max-lines-readme"))
    assert "summary" in result
    assert "issues" in result


def test_verify_fix_unknown_rule():
    result = json.loads(verify_fix(path="x.ts", rule_id="nonexistent"))
    assert result["summary"]["total"] == 0
