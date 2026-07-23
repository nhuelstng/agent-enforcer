from dataclasses import dataclass
from enforcer import FileContext, Match, Needs
from enforcer.combinators import AllOf, AnyOf, OneOf, Not, NoneOf


@dataclass
class Writer:
    needs: Needs = Needs.RAW

    def find(self, file_ctx, shared_ctx=None):
        if shared_ctx is not None:
            shared_ctx["written"] = True
        return [Match(file=file_ctx.path, line=1, matched_value="writer")]


@dataclass
class Reader:
    needs: Needs = Needs.RAW

    def find(self, file_ctx, shared_ctx=None):
        if shared_ctx and shared_ctx.get("written"):
            return [Match(file=file_ctx.path, line=2, matched_value="reader")]
        return []


def _ctx():
    return FileContext(path="x.py", raw="hello")


def test_allof_shared_ctx_propagates_when_none():
    m = AllOf([Writer(), Reader()])
    matches = m.find(_ctx(), shared_ctx=None)
    assert len(matches) == 2
    values = {mt.matched_value for mt in matches}
    assert values == {"writer", "reader"}


def test_anyof_shared_ctx_propagates_when_none():
    m = AnyOf([Writer(), Reader()])
    matches = m.find(_ctx(), shared_ctx=None)
    assert len(matches) == 2


def test_oneof_shared_ctx_propagates_when_none():
    m = OneOf([Writer(), Reader()])
    matches = m.find(_ctx(), shared_ctx=None)
    assert matches == []


def test_oneof_shared_ctx_single_match_when_only_one_writes():
    @dataclass
    class NoMatch:
        needs: Needs = Needs.RAW
        def find(self, file_ctx, shared_ctx=None):
            return []
    m = OneOf([Writer(), NoMatch()])
    matches = m.find(_ctx(), shared_ctx=None)
    assert len(matches) == 1


def test_not_shared_ctx_propagates_when_none():
    m = Not(Writer(), message_on_absence="absent")
    matches = m.find(_ctx(), shared_ctx=None)
    assert matches == []


def test_noneof_shared_ctx_propagates_when_none():
    m = NoneOf([Writer(), Reader()])
    matches = m.find(_ctx(), shared_ctx=None)
    assert matches == []


def test_allof_explicit_shared_ctx_still_works():
    shared = {}
    m = AllOf([Writer(), Reader()])
    matches = m.find(_ctx(), shared_ctx=shared)
    assert len(matches) == 2
    assert shared.get("written") is True


import pytest
from enforcer.matchers import RegexMatcher


@pytest.mark.parametrize("raw", ["a\n", "a b\n", "aaa\n"])
def test_shared_ctx_flags_violation(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AllOf([RegexMatcher(r"a")]).find(ctx, shared_ctx={})
    assert result


@pytest.mark.parametrize("raw", ["\n", "z\n", "qqq\n"])
def test_shared_ctx_passes_clean(raw):
    ctx = FileContext(path="x.py", raw=raw)
    result = AllOf([RegexMatcher(r"a")]).find(ctx, shared_ctx={})
    assert not result
