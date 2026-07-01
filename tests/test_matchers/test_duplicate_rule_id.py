"""Tests for DuplicateRuleIdMatcher: flags config files with duplicate Rule id= values."""
import pytest
from enforcer.matchers.duplicate_rule_id import DuplicateRuleIdMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "config.py") -> FileContext:
    return FileContext(path=path, raw=source)


_DUP = '''\
Rule(id="foo", severity=Severity.ERROR)
Rule(id="bar", severity=Severity.ERROR)
Rule(id="foo", severity=Severity.WARN)
'''

_UNIQUE = '''\
Rule(id="alpha", severity=Severity.ERROR)
Rule(id="beta", severity=Severity.WARN)
Rule(id="gamma", severity=Severity.INFO)
'''

_TRIPLE_DUP = '''\
Rule(id="x", severity=Severity.ERROR)
Rule(id="x", severity=Severity.WARN)
Rule(id="x", severity=Severity.INFO)
'''

_SINGLE_QUOTES = '''\
Rule(id='alpha', severity=Severity.ERROR)
Rule(id='alpha', severity=Severity.WARN)
'''

_EMPTY = ''


class TestDuplicateRuleIdFlags:
    """flags config files with duplicate Rule id= values."""

    @pytest.mark.parametrize("source,expected_id", [
        (_DUP, "foo"),
        (_TRIPLE_DUP, "x"),
        (_SINGLE_QUOTES, "alpha"),
    ])
    def test_flags_duplicate(self, source, expected_id):
        ctx = _make_ctx(source)
        matches = DuplicateRuleIdMatcher().find(ctx)
        assert len(matches) >= 1
        assert all(m.matched_value == expected_id for m in matches)

    def test_triple_dup_yields_two_matches(self):
        ctx = _make_ctx(_TRIPLE_DUP)
        matches = DuplicateRuleIdMatcher().find(ctx)
        assert len(matches) == 2


class TestDuplicateRuleIdClean:
    """does not flag unique or empty configs."""

    @pytest.mark.parametrize("source", [
        _UNIQUE,
        _EMPTY,
        'Rule(id="solo", severity=Severity.ERROR)\n',
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert DuplicateRuleIdMatcher().find(ctx) == []

    def test_needs_raw(self):
        assert DuplicateRuleIdMatcher().needs == Needs.RAW

    def test_no_raw_returns_empty(self):
        ctx = FileContext(path="x.py", raw=None)
        assert DuplicateRuleIdMatcher().find(ctx) == []
