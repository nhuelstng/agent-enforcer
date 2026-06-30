"""Tests for TestCoverageMatcher: enforces positive+negative parameterized test coverage."""
import pytest
from pathlib import Path
from enforcer.matchers.test_coverage import TestCoverageMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(test_source: str, path: str = "test_x.py") -> FileContext:
    ctx = FileContext(path=path, raw=test_source)
    from enforcer.parsers.tree_sitter import parse
    ctx.ast = parse(test_source, Needs.AST_PY)
    return ctx


_GOOD_TEST = '''\
import pytest
from enforcer.matchers.regex import RegexMatcher

class TestRegexMatcherFlags:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_flagged(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert len(matches) == 1

class TestRegexMatcherClean:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_no_match(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert not matches
'''


_MISSING_NEGATIVE = '''\
import pytest
from enforcer.matchers.regex import RegexMatcher

class TestRegexMatcherFlags:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_flagged(self, line):
        matches = RegexMatcher(r"x").find(FileContext(path="x", raw=line))
        assert len(matches) == 1
'''

_MISSING_POSITIVE = '''\
import pytest
class TestClean:
    @pytest.mark.parametrize("line", ["a", "b", "c"])
    def test_no_match(self, line):
        assert not []
'''

_UNDER_PARAMETRIZED = '''\
import pytest
class TestFlags:
    @pytest.mark.parametrize("line", ["a"])
    def test_flagged(self, line):
        assert True

class TestClean:
    @pytest.mark.parametrize("line", ["a"])
    def test_no_match(self, line):
        assert not []
'''

_NO_PARAMETRIZE = '''\
class TestFlags:
    def test_flagged(self):
        assert True

class TestClean:
    def test_no_match(self):
        assert not []
'''


class TestTestCoverageMatcherFlags:
    """flags test files missing positive or negative coverage, or under-parameterized."""

    @pytest.mark.parametrize("source,expected_substring", [
        (_MISSING_NEGATIVE, "negative"),
        (_MISSING_POSITIVE, "positive"),
        (_UNDER_PARAMETRIZED, "parametr"),
        (_NO_PARAMETRIZE, "parametr"),
    ])
    def test_flags_violating_test_file(self, source, expected_substring):
        ctx = _make_ctx(source)
        matcher = TestCoverageMatcher()
        matches = matcher.find(ctx)
        assert len(matches) >= 1
        assert expected_substring.lower() in matches[0].matched_value.lower() or expected_substring.lower() in matches[0].message.lower()


class TestTestCoverageMatcherClean:
    """does not flag test files with both positive and negative, each parameterized >=3."""

    @pytest.mark.parametrize("source", [
        _GOOD_TEST,
    ])
    def test_no_match_on_good_file(self, source):
        ctx = _make_ctx(source)
        matcher = TestCoverageMatcher()
        matches = matcher.find(ctx)
        assert matches == []

    def test_needs_ast_py(self):
        assert TestCoverageMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="class TestX:\n    pass\n")
        matcher = TestCoverageMatcher()
        assert matcher.find(ctx) == []
