import pytest
from unittest.mock import Mock, patch
from enforcer import Severity, FileContext, Match, LLMConsequence
from enforcer.matchers import LineCountMatcher
from enforcer.rule import Rule
from enforcer.llm import LLMExecutor

def test_llm_fires_on_rule_failure():
    mock_response = Mock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Lines 45-80 too verbose"}}]}
    with patch("httpx.post", return_value=mock_response):
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="custom", model="test-model", prompt="Analyze verbosity."),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=30)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    assert matches[0].llm_response == "Lines 45-80 too verbose"

def test_llm_skipped_when_rule_passes():
    with patch("httpx.post") as mock_post:
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=200)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="custom", model="test", prompt="x"),
        )
        ctx = FileContext(path="README.md", raw="short file")
        matches = rule.check(ctx, {})
        assert matches == []
        mock_post.assert_not_called()

def test_llm_no_llm_flag():
    with patch("httpx.post") as mock_post:
        rule = Rule(
            id="verbose-readme",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"],
            message="Too long",
            llm_consequence=LLMConsequence(provider="custom", model="test", prompt="x"),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=30, enabled=False)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    mock_post.assert_not_called()
    assert len(matches) == 1
    assert matches[0].llm_response == ""

def test_llm_timeout():
    import httpx
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        rule = Rule(
            id="test", severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=2)],
            file_globs=["README.md"], message="x",
            llm_consequence=LLMConsequence(provider="custom", model="test", prompt="x", timeout=1),
        )
        ctx = FileContext(path="README.md", raw="line1\nline2\nline3\n")
        matches = rule.check(ctx, {})
        executor = LLMExecutor(concurrency=5, timeout=1)
        matches = executor.execute(matches, rule.llm_consequence, file_ctx=ctx)

    assert matches[0].llm_response == ""

def test_llm_construction():
    executor = LLMExecutor(concurrency=3, timeout=60)
    assert executor.concurrency == 3
    assert executor.timeout == 60
    assert executor.enabled is True
