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
