import pytest
from unittest.mock import patch, mock_open
from enforcer import Severity
from enforcer.context import FileContextBuilder
from enforcer.matchers import RegexMatcher
from enforcer.rule import Rule

def test_file_read_once():
    """Multiple rules targeting same file -> file read exactly once."""
    mock_data = "const #fff;"
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="c", severity=Severity.ERROR, matchers=[RegexMatcher(r"\bconst\b")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    with patch("builtins.open", mock_open(read_data=mock_data)) as mock_file:
        builder.build("x.ts")
        builder.build("x.ts")  # second call should use cache
        # First call reads; second uses cache
        assert mock_file.call_count == 1
