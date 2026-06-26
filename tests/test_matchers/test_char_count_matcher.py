from enforcer import FileContext, Needs
from enforcer.matchers import CharCountMatcher

def test_char_count_exceeds():
    ctx = FileContext(path="x.ts", raw="x" * 101)
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "101"

def test_char_count_at_limit():
    ctx = FileContext(path="x.ts", raw="x" * 100)
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_below_limit():
    ctx = FileContext(path="x.ts", raw="short")
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_empty_file():
    ctx = FileContext(path="x.ts", raw="")
    matches = CharCountMatcher(max_chars=100).find(ctx)
    assert matches == []

def test_char_count_needs_raw():
    assert CharCountMatcher(max_chars=10).needs == Needs.RAW
