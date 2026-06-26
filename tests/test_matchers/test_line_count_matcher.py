from enforcer import FileContext, Needs
from enforcer.matchers import LineCountMatcher

def test_line_count_exceeds():
    ctx = FileContext(path="README.md", raw="\n".join(["line"] * 201))
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "201"

def test_line_count_at_limit():
    ctx = FileContext(path="README.md", raw="\n".join(["line"] * 200))
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_below_limit():
    ctx = FileContext(path="README.md", raw="one line")
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_empty_file():
    ctx = FileContext(path="README.md", raw="")
    matches = LineCountMatcher(max_lines=200).find(ctx)
    assert matches == []

def test_line_count_needs_raw():
    assert LineCountMatcher(max_lines=10).needs == Needs.RAW
