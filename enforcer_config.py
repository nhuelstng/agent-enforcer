import re
from enforcer import (
    Rule, Severity, LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher, LineCountMatcher, PathNotMatchingMatcher,
    AllowlistMatcher, AlwaysMatcher, FileExistsMatcher,
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
    Rule(
        id="function-focus",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="function-focus-check")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/*.d.ts"],
        message="Functions should be short, focused, and single-purpose.",
        fix_instruction="Consider splitting large functions into smaller, focused units.",
        llm_consequence=LLMConsequence(
            provider="default",
            model="gpt-4",
            prompt="Review this file's functions. Are they short, focused, and single-purpose? Flag any that are too long or do multiple things. Be concise.",
        ),
    ),
    Rule(
        id="test-file-exists",
        severity=Severity.WARN,
        matchers=[Not(FileExistsMatcher(read_target="**/*.spec.ts"))],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/*.d.ts", "**/index.ts"],
        message="No test file found for '{file}'. Agents must write tests.",
        fix_instruction="Create a .spec.ts file alongside the source file.",
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
