from enforcer.matchers import AlwaysMatcher
from enforcer.types import FileContext


def test_always_matcher_matches_non_empty_file():
    ctx = FileContext(path="x.ts", raw="const x = 1;\n")
    matcher = AlwaysMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert matches[0].file == "x.ts"
    assert matches[0].matched_value == "(always)"


def test_always_matcher_skips_empty_file():
    ctx = FileContext(path="x.ts", raw=None)
    matcher = AlwaysMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 0


def test_always_matcher_custom_value():
    ctx = FileContext(path="x.ts", raw="code")
    matcher = AlwaysMatcher(matched_value="check-me")
    matches = matcher.find(ctx)
    assert matches[0].matched_value == "check-me"


import pytest


@pytest.mark.parametrize("raw", ["a", "code", "x = 1"])
def test_always_flags_violation(raw):
    assert AlwaysMatcher().find(FileContext(path="x.py", raw=raw))


@pytest.mark.parametrize("raw", [None, None, None])
def test_always_passes_clean(raw):
    assert not AlwaysMatcher().find(FileContext(path="x.py", raw=raw))
