from enforcer.extractors import EnvFileKeys


def test_env_file_happy_path():
    raw = "FOO=bar\nBAZ=qux\n# comment\n\nQUUX= "
    assert EnvFileKeys().extract(raw) == {"FOO", "BAZ", "QUUX"}


def test_env_file_skips_comments_and_blanks():
    raw = "# header\n\nKEY=value\n  # indented comment\nOTHER=1"
    assert EnvFileKeys().extract(raw) == {"KEY", "OTHER"}


def test_env_file_empty_string():
    assert EnvFileKeys().extract("") == set()


def test_env_file_no_equals():
    raw = "JUST_A_KEY\nANOTHER"
    assert EnvFileKeys().extract(raw) == set()


def test_env_file_value_contains_equals():
    raw = "URL=http://example.com?x=1&y=2"
    assert EnvFileKeys().extract(raw) == {"URL"}


def test_env_file_strips_whitespace_around_key():
    raw = "  SPACED  =value\n\tTABBED\t=1"
    assert EnvFileKeys().extract(raw) == {"SPACED", "TABBED"}


import pytest


@pytest.mark.parametrize("raw,key", [
    ("FOO=bar", "FOO"),
    ("A=1\nB=2", "B"),
    ("URL=http://example.com", "URL"),
])
def test_env_extracts_key(raw, key):
    """KEY names before '=' are present in the extracted set."""
    assert key in EnvFileKeys().extract(raw)


@pytest.mark.parametrize("raw,key", [
    ("FOO=bar", "BAR"),
    ("# just a comment", "comment"),
    ("NOEQUALS", "NOEQUALS"),
])
def test_env_absent_key(raw, key):
    """Comments, value tokens, and keyless lines produce no such key."""
    assert not (key in EnvFileKeys().extract(raw))
