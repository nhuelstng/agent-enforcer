import pytest
from enforcer import Needs, Severity
from enforcer.context import FileContextBuilder
from enforcer.matchers import RegexMatcher, LineCountMatcher
from enforcer.rule import Rule

def test_builder_provides_raw():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    ctx = builder.build("tests/fixtures/sample.ts")
    assert ctx.raw is not None
    assert ctx.path == "tests/fixtures/sample.ts"

def test_builder_aggregates_needs():
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
        Rule(id="b", severity=Severity.ERROR, matchers=[LineCountMatcher(max_lines=10)],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    needs = builder.needs_for_file("x.ts", rules)
    assert Needs.RAW in needs

def test_builder_missing_file_returns_none_raw():
    """Building a context for a nonexistent file should return raw=None."""
    rules = [
        Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
             file_globs=["**/*.ts"], message="x"),
    ]
    builder = FileContextBuilder(rules, workspace=".")
    ctx = builder.build("nonexistent_file.ts")
    assert ctx.raw is None

def test_builder_empty_file_has_raw_not_none():
    """An empty file should have raw='' (not None) so matchers can process it."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "empty.ts").write_text("")
        rules = [
            Rule(id="a", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")],
                 file_globs=["**/*.ts"], message="x"),
        ]
        builder = FileContextBuilder(rules, workspace=tmpdir)
        ctx = builder.build("empty.ts")
        assert ctx.raw is not None
        assert ctx.raw == ""
