"""Tests for AllSortedMatcher: flags __all__ lists not alphabetically sorted."""
import pytest
from enforcer.matchers.all_sorted import AllSortedMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    return FileContext(path=path, raw=source)


_UNSORTED = '''\
__all__ = [
    "Zebra",
    "Apple",
    "Mango",
]
'''

_SORTED = '''\
__all__ = [
    "Apple",
    "Mango",
    "Zebra",
]
'''

_UNSORTED_SINGLE_LINE = '__all__ = ["Banana", "Apple", "Cherry"]\n'

_SORTED_SINGLE_LINE = '__all__ = ["Apple", "Banana", "Cherry"]\n'

_NO_ALL = '''\
def foo():
    pass
'''

_SINGLE_ENTRY = '__all__ = ["Solo"]\n'


class TestAllSortedFlags:
    """flags __all__ lists that are not alphabetically sorted."""

    @pytest.mark.parametrize("source", [
        _UNSORTED,
        _UNSORTED_SINGLE_LINE,
    ])
    def test_flags_unsorted(self, source):
        ctx = _make_ctx(source)
        matches = AllSortedMatcher().find(ctx)
        assert len(matches) == 1

    def test_unsorted_flags_correct_line(self):
        ctx = _make_ctx(_UNSORTED)
        matches = AllSortedMatcher().find(ctx)
        assert matches[0].line == 1


class TestAllSortedClean:
    """does not flag sorted, missing, or single-entry __all__."""

    @pytest.mark.parametrize("source", [
        _SORTED,
        _SORTED_SINGLE_LINE,
        _NO_ALL,
        _SINGLE_ENTRY,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert AllSortedMatcher().find(ctx) == []

    def test_needs_raw(self):
        assert AllSortedMatcher().needs == Needs.RAW

    def test_no_raw_returns_empty(self):
        ctx = FileContext(path="x.py", raw=None)
        assert AllSortedMatcher().find(ctx) == []
