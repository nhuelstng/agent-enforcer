"""Convention-as-code entry point.

Loaded by ``enforcer.config.load_config()`` (and the pre-commit hook / MCP
server via ``ENFORCER_CONFIG``). This module defines conventions declaratively
through four magic module attributes that ``load_config`` introspects:

Magic module attributes
-----------------------
``RULES`` : list[Rule]
    Ordered list of convention rules to enforce.
``WORKSPACE`` : str
    Root directory the rules resolve paths against (default ``"."``).
``SEVERITY_ACTIONS`` : dict[Severity, str]
    Maps each ``Severity`` to the action the runner takes on a match:
    - ``"block"``      -> exit 1 immediately (ERROR).
    - ``"block_warn"``  -> exit 1 unless ``--confirm-read-warnings`` is passed
                          (WARN); lets a human/agent acknowledge the warning.
    - ``"print"``      -> non-blocking, emitted to stdout (INFO-ish).
    - ``"hint"``       -> advisory only, never blocks.
``LLM_CONFIG`` : dict
    LLM execution tuning: ``concurrency`` (parallel LLM calls) and
    ``timeout`` (per-call seconds).

Available matchers (enforcer.matchers)
--------------------------------------
RegexMatcher, LineCountMatcher, CharCountMatcher, PathNotMatchingMatcher,
AllowlistMatcher, AstNodeMatcher, CommentPerFunctionMatcher, AlwaysMatcher,
FileExistsMatcher.

Available combinators (enforcer.combinators)
---------------------------------------------
AllOf, AnyOf, OneOf, Not, NoneOf.

Available predicates (enforcer.predicates)
-----------------------------------------
IntPredicate, StringLengthPredicate, StringMatchesPredicate,
StringNotMatchesPredicate, All, Any, NotP.

Rule fields
-----------
``id``               : stable rule identifier.
``severity``         : Severity.ERROR | WARN | INFO.
``matchers``         : list of matcher instances (combined with AllOf).
``file_globs``       : globs a file must match to be checked.
``exclude_globs``    : globs that skip a file even if ``file_globs`` match.
``read_targets``     : extra files read into the shared context (e.g. an
                        allowlist) so matchers can cross-reference them.
``message``          : str with ``{file}``/``{line}``/``{column}``/
                        ``{matched_value}`` placeholders, or a Callable.
``fix_instruction``  : short human/agent-readable fix hint.
``llm_consequence``  : optional LLMConsequence for natural-language review.
``workspace``        : per-rule workspace override (defaults to module WORKSPACE).

LLMConsequence fields
---------------------
``provider``  : LLM provider key.
``prompt``    : prompt template sent to the provider.
``timeout``   : per-call override (seconds).
``model``     : model identifier.
"""
from enforcer import (
    Rule, Severity, LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher, LineCountMatcher, PathNotMatchingMatcher,
    AlwaysMatcher, FileExistsMatcher,
)
from enforcer.combinators import Not

WORKSPACE = "."

RULES = [
    # RegexMatcher + exclude_globs + read_targets (cross-file allowlist) + {matched_value} templating
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
    # LineCountMatcher + IntPredicate to cap file length
    Rule(
        id="max-lines-readme",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=200)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 200).",
    ),
    # AlwaysMatcher + LLMConsequence for natural-language convention review
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
    # Not(FileExistsMatcher) to enforce 'test file must exist' for each source file
    Rule(
        id="test-file-exists",
        severity=Severity.WARN,
        matchers=[Not(FileExistsMatcher(read_target="**/*.spec.ts"))],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/*.d.ts", "**/index.ts"],
        message="No test file found for '{file}'. Agents must write tests.",
        fix_instruction="Create a .spec.ts file alongside the source file.",
    ),
    # AlwaysMatcher as warning trigger for manual review (WARN severity, blocks until confirmed)
    Rule(
        id="css-duplicate-check",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="css-duplicate-check")],
        file_globs=["**/*.css"],
        message="Make sure you did not create a duplicate.",
        fix_instruction="Review the file for duplicate selectors or properties.",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}

LLM_CONFIG = {
    "concurrency": 5,
    "timeout": 30,
}
