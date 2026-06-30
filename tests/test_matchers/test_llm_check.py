"""Tests for LLMMatcher: LLM-as-check matcher with structured JSON output and text fallback."""
import json
from unittest.mock import Mock, patch
from enforcer.types import FileContext, Needs, LLMConfig, ProviderConfig
from enforcer.matchers.llm_check import LLMMatcher

_LLM_CFG = LLMConfig(default_provider="test", default_model="test-model", providers={
    "test": ProviderConfig(base_url="http://localhost/v1", token_env="", headers={}),
})


def _mock_httpx_response(content: str):
    mock = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock


def test_llm_matcher_pass_returns_no_match():
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="Is this code good?")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
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
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
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
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert len(matches) == 1
    assert matches[0].file == "ctx.py"
    assert matches[0].line == 5


def test_llm_matcher_json_missing_line_defaults_to_zero():
    violations = {"violations": [{"file": "foo.py", "reason": "issue"}]}
    response = _mock_httpx_response(json.dumps(violations))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert len(matches) == 1
    assert matches[0].line == 0


def test_llm_matcher_json_parse_fail_falls_back_to_pass_text():
    response = _mock_httpx_response("PASS — looks good")
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert matches == []


def test_llm_matcher_json_parse_fail_falls_back_to_fail_text():
    response = _mock_httpx_response("FAIL: something is wrong here")
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert len(matches) == 1
    assert matches[0].line == 0
    assert "FAIL" in matches[0].matched_value


def test_llm_matcher_metadata_phase_prompt_has_end_marker():
    """METADATA-phase prompt should include END CHANGE CONTEXT marker for injection defense."""
    from enforcer.types import ChangeContext
    cc = ChangeContext(commit_msg="feat: add foo", modified=["foo.py"])
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response) as mock_post:
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path=".", raw="__enforcer_sentinel__")
        m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG, "__change__": cc})
    sent_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "--- END CHANGE CONTEXT ---" in sent_prompt

def test_llm_matcher_llm_error_fail_open():
    import httpx
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        m = LLMMatcher(prompt="x", timeout=1)
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert matches == []


def test_llm_matcher_disabled_when_llm_not_enabled():
    with patch("httpx.post") as mock_post:
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": False, "__llm_config__": _LLM_CFG})
    assert matches == []
    mock_post.assert_not_called()


def test_llm_matcher_no_shared_ctx_still_works():
    """Matcher called standalone (shared_ctx=None) should not crash — defaults to enabled."""
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x", provider="test", model="test-model")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_config__": _LLM_CFG})
    assert matches == []


def test_llm_matcher_metadata_phase_uses_change_context():
    """In METADATA phase, file_ctx.raw is the sentinel. Matcher builds prompt from ChangeContext instead."""
    from enforcer.types import ChangeContext
    cc = ChangeContext(commit_msg="feat: add foo", modified=["foo.py"])
    response = _mock_httpx_response(json.dumps({"pass": True}))
    with patch("httpx.post", return_value=response) as mock_post:
        m = LLMMatcher(prompt="Does commit msg align with changes?")
        ctx = FileContext(path=".", raw="__enforcer_sentinel__")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG, "__change__": cc})
    assert matches == []
    # Verify the prompt sent to LLM includes the commit message
    call_args = mock_post.call_args
    sent_prompt = call_args.kwargs["json"]["messages"][0]["content"]
    assert "feat: add foo" in sent_prompt


def test_llm_matcher_metadata_phase_no_change_context_returns_empty():
    """METADATA phase without ChangeContext — nothing to check."""
    ctx = FileContext(path=".", raw="__enforcer_sentinel__")
    m = LLMMatcher(prompt="x")
    matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
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
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG, "__change__": cc})
    assert len(matches) == 1
    assert matches[0].line == 0
    assert "FAIL" in matches[0].matched_value


def test_llm_matcher_strips_prose_around_json():
    """LLM response with prose before/after JSON must still parse correctly."""
    response_text = (
        "Let me analyze this code.\n\n"
        '{"violations": [{"file": "foo.py", "line": 3, "reason": "bad name"}]}\n\n'
        "That's all I found."
    )
    response = _mock_httpx_response(response_text)
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="Check conventions")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert len(matches) == 1
    assert matches[0].file == "foo.py"
    assert matches[0].line == 3
    assert matches[0].matched_value == "bad name"


def test_llm_matcher_strips_markdown_code_fences():
    """JSON wrapped in markdown code fences must parse correctly."""
    response_text = "```json\n{\"pass\": true}\n```"
    response = _mock_httpx_response(response_text)
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert matches == []


def test_llm_matcher_strips_think_tags_from_response():
    """Reasoning blocks 国小...</think> must be stripped before parsing."""
    response_text = "国小Let me think about this.\nThe code looks fine.\n国B{\"pass\": true}"
    response = _mock_httpx_response(response_text)
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert matches == []


def test_llm_matcher_malformed_json_repaired():
    """Malformed JSON (missing quotes, trailing commas) should be repaired, not dumped as raw text."""
    response_text = '{"violations": [{file: "foo.py", line: 3, reason: "bad",}]}'
    response = _mock_httpx_response(response_text)
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="Check conventions")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert len(matches) == 1
    assert matches[0].file == "foo.py"
    assert matches[0].line == 3
    assert matches[0].matched_value == "bad"


def test_llm_matcher_pure_prose_fail_open():
    """Response with no JSON and no PASS/FAIL marker should fail-open (no matches), not dump reasoning."""
    response_text = "I analyzed the code and it looks fine to me. No issues found."
    response = _mock_httpx_response(response_text)
    with patch("httpx.post", return_value=response):
        m = LLMMatcher(prompt="x")
        ctx = FileContext(path="foo.py", raw="x = 1\n")
        matches = m.find(ctx, {"__llm_enabled__": True, "__llm_config__": _LLM_CFG})
    assert matches == []
