"""Tests for LLMMatcher: LLM-as-check matcher with structured JSON output and text fallback."""
import json
from unittest.mock import Mock, patch
from enforcer.types import FileContext, Needs
from enforcer.matchers.llm_check import LLMMatcher


def _mock_httpx_response(content: str):
    mock = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock


def test_llm_matcher_pass_returns_no_match():
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="Is this code good?")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert matches == []


def test_llm_matcher_fail_json_returns_structured_matches():
    violations = {"violations": [
        {"file": "foo.py", "line": 3, "reason": "bad name"},
        {"file": "bar.py", "line": 10, "reason": "too long"},
    ]}
    response = _mock_httpx_response(json.dumps(violations))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="Check conventions")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert len(matches) == 2
    assert matches[0].file == "foo.py"
    assert matches[0].line == 3
    assert matches[0].matched_value == "bad name"
    assert matches[1].file == "bar.py"
    assert matches[1].line == 10


def test_llm_matcher_json_missing_file_defaults_to_ctx_path():
    violations = {"violations": [{"line": 5, "reason": "issue"}]}
    response = _mock_httpx_response(json.dumps(violations))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="ctx.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert len(matches) == 1
    assert matches[0].file == "ctx.py"
    assert matches[0].line == 5


def test_llm_matcher_json_missing_line_defaults_to_zero():
    violations = {"violations": [{"file": "foo.py", "reason": "issue"}]}
    response = _mock_httpx_response(json.dumps(violations))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert len(matches) == 1
    assert matches[0].line == 0


def test_llm_matcher_json_parse_fail_falls_back_to_pass_text():
    response = _mock_httpx_response("PASS — looks good")
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert matches == []


def test_llm_matcher_json_parse_fail_falls_back_to_fail_text():
    response = _mock_httpx_response("FAIL: something is wrong here")
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert len(matches) == 1
    assert matches[0].line == 0
    assert "FAIL" in matches[0].matched_value
    assert matches[0].file == "foo.py"


def test_llm_matcher_llm_error_fail_open():
    import httpx
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        m = LLMMatcher(prompt="x", timeout=1)
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True})
    assert matches == []


def test_llm_matcher_disabled_when_llm_not_enabled():
    with patch("httpx.post") as mock_post:
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": False})
    assert matches == []
    mock_post.assert_not_called()


def test_llm_matcher_no_shared_ctx_still_works():
    """Matcher called standalone (shared_ctx=None) should not crash — defaults to enabled."""
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, None)
    assert matches == []


def test_llm_matcher_metadata_phase_uses_change_context():
    """In METADATA phase, file_ctx.raw is the sentinel. Matcher builds prompt from ChangeContext instead."""
    from enforcer.types import ChangeContext
    cc = ChangeContext(commit_msg="feat: add foo", modified=["foo.py"])
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response) as mock_post:
        m = LLMMatcher(prompt="Does commit msg align with changes?")
        ctx = FileContext(path=".", raw="__enforcer_sentinel__")
        matches = m.find(ctx, {"__llm_enabled__": True, "__change__": cc})
    assert matches == []
    # Verify the prompt sent to LLM includes the commit message
    call_args = mock_post.call_args
    sent_prompt = call_args.kwargs["json"]["messages"][0]["content"]
    assert "feat: add foo" in sent_prompt


def test_llm_matcher_metadata_phase_no_change_context_returns_empty():
    """METADATA phase without ChangeContext — nothing to check."""
    ctx = FileContext(path=".", raw="__enforcer_sentinel__")
    m = LLMMatcher(prompt="x")
    matches = m.find(ctx, {"__llm_enabled__": True})
    assert matches == []


def test_llm_matcher_needs_raw():
    m = LLMMatcher(prompt="x")
    assert m.needs == Needs.RAW


def test_llm_matcher_metadata_phase_fail_returns_match():
    """METADATA-phase FAIL produces a match on the workspace path."""
    from enforcer.types import ChangeContext
    cc = ChangeContext(commit_msg="garbage", modified=["foo.py"])
    response = _mock_httpx_response("FAIL: message doesn't describe changes")
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path=".", raw="__enforcer_sentinel__")
        matches = m.find(ctx, {"__llm_enabled__": True, "__change__": cc})
    assert len(matches) == 1
    assert matches[0].line == 0
    assert "FAIL" in matches[0].matched_value
