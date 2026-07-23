"""Tests for rule_view: the reflection seam shared by docs and explain."""
from pathlib import Path
from enforcer.rule_view import parse_docstring_sections, matcher_sections, paired_test
from enforcer.matchers import RegexMatcher


def test_parse_docstring_sections_extracts_labels():
    doc = "Summary line.\n\nWhat:       flags X\nIgnores:    Y\nBasis:      RAW\n"
    sections = parse_docstring_sections(doc)
    assert sections["What"] == "flags X"
    assert sections["Ignores"] == "Y"
    assert sections["Basis"] == "RAW"


def test_parse_docstring_sections_empty_for_none():
    assert parse_docstring_sections(None) == {}
    assert parse_docstring_sections("no labelled sections here") == {}


def test_matcher_sections_reads_class_docstring():
    """matcher_sections reflects a real matcher's structured docstring."""
    sections = matcher_sections(RegexMatcher("x"))
    assert "What" in sections


def test_paired_test_finds_existing_matcher_test():
    """paired_test resolves a matcher class to its tests/test_matchers/ file."""
    ws = str(Path(__file__).resolve().parent.parent)
    found = paired_test("RegexMatcher", ws)
    assert found is not None
    assert found.name == "test_regex_matcher.py"


def test_paired_test_none_for_unknown_class():
    ws = str(Path(__file__).resolve().parent.parent)
    assert paired_test("NoSuchMatcherXyz", ws) is None
