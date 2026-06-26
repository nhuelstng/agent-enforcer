import pytest
from enforcer.context import FileContextBuilder
from enforcer.types import Needs, FileContext
from enforcer.rule import Rule, _is_combinator
from enforcer.combinators import Not, AllOf
from enforcer.matchers import RegexMatcher
from enforcer.types import Severity


class TestIsCombinator:
    def test_not_detected_as_combinator(self):
        matcher = Not(RegexMatcher(r"TODO"))
        assert _is_combinator(matcher) is True

    def test_allof_detected_as_combinator(self):
        matcher = AllOf([RegexMatcher(r"TODO"), RegexMatcher(r"FIXME")])
        assert _is_combinator(matcher) is True

    def test_plain_matcher_not_combinator(self):
        matcher = RegexMatcher(r"TODO")
        assert _is_combinator(matcher) is False
