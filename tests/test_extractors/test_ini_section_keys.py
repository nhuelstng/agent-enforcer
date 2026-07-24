from enforcer.extractors import IniSectionKeys


def test_ini_happy_path():
    raw = "[default]\nfoo = bar\nbaz = qux\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="default").extract(raw) == {"foo", "baz"}


def test_ini_other_section():
    raw = "[default]\nfoo = bar\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="other").extract(raw) == {"key"}


def test_ini_missing_section():
    raw = "[default]\nfoo = bar\n"
    assert IniSectionKeys(section="nonexistent").extract(raw) == set()


def test_ini_empty_string():
    assert IniSectionKeys(section="default").extract("") == set()


def test_ini_malformed():
    raw = "not an ini file\njust text\n"
    assert IniSectionKeys(section="default").extract(raw) == set()


def test_ini_section_with_no_keys():
    raw = "[default]\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="default").extract(raw) == set()


import pytest


@pytest.mark.parametrize("raw,key", [
    ("[default]\nfoo = bar\n", "foo"),
    ("[default]\na = 1\nb = 2\n", "b"),
    ("[default]\nx = 1\ny = 2\nz = 3\n", "z"),
])
def test_ini_extracts_key(raw, key):
    """Keys inside the named section are present in the extracted set."""
    assert key in IniSectionKeys(section="default").extract(raw)


@pytest.mark.parametrize("raw,key", [
    ("[default]\nfoo = bar\n", "baz"),
    ("[other]\nkey = val\n", "key"),
    ("", "foo"),
])
def test_ini_absent_key(raw, key):
    """Keys outside the section, or absent entirely, are not extracted."""
    assert not (key in IniSectionKeys(section="default").extract(raw))
