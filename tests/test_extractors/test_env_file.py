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
