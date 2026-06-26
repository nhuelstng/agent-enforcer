import pytest
from enforcer import FileContext, Needs
from enforcer.matchers import RegexMatcher

def test_regex_finds_all_matches():
    ctx = FileContext(path="x.ts", raw="color: #fff; bg: #aabbcc; border: #123456;")
    matcher = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")
    matches = matcher.find(ctx)
    assert len(matches) == 3
    assert matches[0].matched_value == "#fff"
    assert matches[0].line == 1
    assert matches[0].column == 8
    assert matches[1].matched_value == "#aabbcc"
    assert matches[2].matched_value == "#123456"

def test_regex_multiline():
    ctx = FileContext(path="x.ts", raw="color: #fff;\nbg: #aabbcc;\n")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert len(matches) == 2
    assert matches[0].line == 1
    assert matches[1].line == 2

def test_regex_no_matches():
    ctx = FileContext(path="x.ts", raw="color: var(--color-primary);")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert matches == []

def test_regex_empty_file():
    ctx = FileContext(path="x.ts", raw="")
    matches = RegexMatcher(r"#[0-9a-fA-F]{3,6}\b").find(ctx)
    assert matches == []

def test_regex_needs_raw():
    assert RegexMatcher(r"test").needs == Needs.RAW

def test_regex_column_position():
    ctx = FileContext(path="x.ts", raw="  #fff")
    matches = RegexMatcher(r"#fff").find(ctx)
    assert matches[0].column == 3

def test_regex_matches_file_field():
    ctx = FileContext(path="x.ts", raw="#fff")
    matches = RegexMatcher(r"#fff").find(ctx)
    assert matches[0].file == "x.ts"
