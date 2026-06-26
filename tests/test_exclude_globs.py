from enforcer import Severity, FileContext
from enforcer.rule import Rule
from enforcer.matchers import RegexMatcher

def test_exclude_single_pattern():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts"],
    )
    assert rule.check(FileContext(path="a.spec.ts", raw="#fff"), {}) == []
    assert len(rule.check(FileContext(path="a.ts", raw="#fff"), {})) == 1

def test_exclude_directory():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/generated/**"],
    )
    assert rule.check(FileContext(path="generated/a.ts", raw="#fff"), {}) == []

def test_exclude_wildcard_prefix():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.scss"],
        exclude_globs=["**/material-theme*"],
    )
    assert rule.check(FileContext(path="material-theme.scss", raw="#fff"), {}) == []
    assert len(rule.check(FileContext(path="colors.scss", raw="#fff"), {})) == 1

def test_no_exclude_globs():
    rule = Rule(
        id="x", severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
    )
    assert len(rule.check(FileContext(path="a.spec.ts", raw="#fff"), {})) == 1
