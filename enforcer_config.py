import re
from enforcer import (
    Rule, Severity, LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher, LineCountMatcher, PathNotMatchingMatcher,
    AllowlistMatcher,
)
from enforcer.combinators import AnyOf, AllOf, Not
from enforcer.predicates import IntPredicate

WORKSPACE = "."

RULES = [
    Rule(
        id="no-raw-hex",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
        file_globs=["**/*.ts", "**/*.tsx", "**/*.scss"],
        exclude_globs=["**/*.spec.ts", "**/material-theme.scss", "**/generated/**"],
        workspace="frontend/",
        read_targets=["**/colors.scss"],
        message="Raw hex color '{matched_value}' found. Use var(--color-*) from colors.scss.",
        fix_instruction="Replace with the appropriate var(--color-*) from colors.scss.",
    ),
    Rule(
        id="max-lines-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=200)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 200).",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "print",
    Severity.INFO: "hint",
}

LLM_CONFIG = {
    "concurrency": 5,
    "timeout": 30,
}
