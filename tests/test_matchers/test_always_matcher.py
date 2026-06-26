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
