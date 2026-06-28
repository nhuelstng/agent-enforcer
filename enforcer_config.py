"""Self-enforcement config for pre-commit-agent-enforcer.

This config enforces the conventions documented in AGENTS.md on this very
repo. It is the dogfood config — the tool checks itself.

Severity philosophy:
  ERROR — style/correctness violations. Always blocks. Must fix before commit.
  WARN  — critical-component reminders. Blocks unless --confirm-read-warnings.
          Fires when you touch files that have broad blast radius. The reminder
          tells you what to verify before acknowledging.

Setup (one-time):
  enforcer install --force
  export ENFORCER_CONFIG=enforcer_config.py

Then every `git commit` runs the rules below against staged files.
"""
from enforcer import (
    Rule,
    Severity,
    RuleType,
    LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher,
    ImportMatcher,
    FunctionComplexityMatcher,
    PairedFileMatcher,
    BranchNameMatcher,
    CommitMessageMatcher,
    NamingConventionMatcher,
    DocstringMatcher,
    AlwaysMatcher,
    LineCountMatcher,
)

WORKSPACE = "."

RULES = [
    # ════════════════════════════════════════════════════════════════════
    # ERROR — style/correctness rules. Always block. Must fix.
    # ════════════════════════════════════════════════════════════════════

    # ─── Git metadata: branch naming ─────────────────────────────────────
    Rule(
        id="branch-naming",
        severity=Severity.ERROR,
        matchers=[BranchNameMatcher(pattern=r"^(feature|fix|hotfix|chore|docs|refactor)/")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Branch '{matched_value}' doesn't match required pattern: type/description",
        fix_instruction="Rename: git branch -m <type>/<description>",
    ),

    # ─── Git metadata: commit message format ─────────────────────────────
    Rule(
        id="commit-message",
        severity=Severity.ERROR,
        matchers=[CommitMessageMatcher(pattern=r"^(feat|fix|docs|refactor|test|chore|perf|ci|build|style|revert)(\(.+\))?:\s+.+")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Commit message '{matched_value}' doesn't follow Conventional Commits",
        fix_instruction="Use: type(scope): description (e.g. feat(matchers): add X)",
    ),

    # ─── Test pairing: every matcher has a test ──────────────────────────
    Rule(
        id="matcher-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/matchers/*.py",
            derived_glob="tests/test_matchers/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py"],
        message="No test file for matcher {file}. Every matcher needs paired tests.",
        fix_instruction="Create tests/test_matchers/test_{stem}.py",
        diff_only=True,
    ),

    # ─── Test pairing: every predicate has a test ─────────────────────────
    Rule(
        id="predicate-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/predicates/*.py",
            derived_glob="tests/test_predicates/test_*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/predicates/*.py"],
        exclude_globs=["enforcer/predicates/__init__.py"],
        message="No test file for predicate {file}. Every predicate needs paired tests.",
        fix_instruction="Create tests/test_predicates/test_{stem}.py",
        diff_only=True,
    ),

    # ─── Test pairing: every combinator has a test ───────────────────────
    Rule(
        id="combinator-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/combinators/*.py",
            derived_glob="tests/test_combinators/test_*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/combinators/*.py"],
        exclude_globs=["enforcer/combinators/__init__.py"],
        message="No test file for combinator {file}. Every combinator needs paired tests.",
        fix_instruction="Create tests/test_combinators/test_{stem}.py",
        diff_only=True,
    ),

    # ─── Test pairing: core modules have tests ───────────────────────────
    Rule(
        id="core-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/*.py",
            derived_glob="tests/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/*.py"],
        exclude_globs=["enforcer/__init__.py", "enforcer/matchers/**", "enforcer/predicates/**", "enforcer/combinators/**", "enforcer/parsers/**"],
        message="No test file for core module {file}.",
        fix_instruction="Create tests/test_{stem}.py",
        diff_only=True,
    ),

    # ─── Naming: functions must be snake_case ───────────────────────────
    Rule(
        id="function-snake-case",
        severity=Severity.ERROR,
        matchers=[NamingConventionMatcher(
            declaration_types=["function_definition"],
            pattern=r"^[a-z_][a-z0-9_]*$",
        )],
        file_globs=["enforcer/**/*.py"],
        message="Function '{matched_value}' at {file}:{line} must be snake_case",
        fix_instruction="Rename to snake_case.",
        diff_only=True,
    ),

    # ─── Naming: classes must be CapWords ───────────────────────────────
    Rule(
        id="class-capwords",
        severity=Severity.ERROR,
        matchers=[NamingConventionMatcher(
            declaration_types=["class_definition"],
            pattern=r"^[A-Z][a-zA-Z0-9]*$",
        )],
        file_globs=["enforcer/**/*.py"],
        message="Class '{matched_value}' at {file}:{line} must be CapWords (PascalCase)",
        fix_instruction="Rename to CapWords.",
        diff_only=True,
    ),

    # ─── No print() in library code ──────────────────────────────────────
    Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found in library code at {file}:{line}. Use sys.stderr.write or structlog.",
        fix_instruction="Replace print() with sys.stderr.write(...).",
    ),

    # ─── No bare except ─────────────────────────────────────────────────
    Rule(
        id="no-bare-except",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*except\s*:")],
        file_globs=["enforcer/**/*.py"],
        message="Bare except: at {file}:{line}. Use except Exception or more specific.",
        fix_instruction="Change to `except Exception:` or a more specific exception.",
    ),

    # ─── No secrets ─────────────────────────────────────────────────────
    Rule(
        id="no-secrets",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]")],
        file_globs=["**/*.py"],
        exclude_globs=["**/test*", "**/*test*"],
        message="Possible hardcoded secret at {file}:{line}. Use env var.",
        fix_instruction="Move to env var or secrets manager.",
    ),

    # ─── Function complexity: max lines ──────────────────────────────────
    Rule(
        id="function-max-lines",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="lines", max_value=75)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has {matched_value} lines (max 75). Split or extract.",
        fix_instruction="Extract sub-functions or move logic to a helper module.",
        diff_only=True,
    ),

    # ─── Function complexity: max params ─────────────────────────────────
    Rule(
        id="function-max-params",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="params", max_value=5)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has {matched_value} parameters (max 5). Group into a dataclass.",
        fix_instruction="Group related parameters into a dataclass and pass as single arg.",
        diff_only=True,
    ),

    # ─── Function complexity: cyclomatic ─────────────────────────────────
    Rule(
        id="cyclomatic-complexity",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="cyclomatic", max_value=10)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has cyclomatic complexity {matched_value} (max 10). Reduce branching.",
        fix_instruction="Extract branches into helper functions or use early returns.",
        diff_only=True,
    ),

    # ─── No wildcard imports ─────────────────────────────────────────────
    Rule(
        id="no-wildcard-imports",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"import\s+\*", r"from\s+\S+\s+import\s+\*"])],
        file_globs=["enforcer/**/*.py"],
        message="Wildcard import at {file}:{line}. Use explicit imports.",
        fix_instruction="Replace `from X import *` with explicit symbol imports.",
        diff_only=True,
    ),

    # ─── TODO needs owner ────────────────────────────────────────────────
    Rule(
        id="todo-needs-owner",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#\s*(TODO|FIXME|HACK|XXX)\b(?!\s*\(@)")],
        file_globs=["enforcer/**/*.py"],
        message="TODO/FIXME without owner at {file}:{line}. Use '# TODO(@name): …' or remove.",
        fix_instruction="Add owner reference or delete the TODO and address now.",
        diff_only=True,
    ),

    # ─── Docstrings on public functions ─────────────────────────────────
    Rule(
        id="docstring-public",
        severity=Severity.ERROR,
        matchers=[DocstringMatcher()],
        file_globs=["enforcer/**/*.py"],
        message="Function '{matched_value}' at {file}:{line} missing docstring. Public functions must be documented.",
        fix_instruction='Add a docstring: """<one-line description>."""',
        diff_only=True,
    ),

    # ─── README length with LLM analysis ─────────────────────────────────
    Rule(
        id="readme-max-lines",
        severity=Severity.ERROR,
        matchers=[LineCountMatcher(max_lines=300)],
        file_globs=["README.md"],
        message="README.md has {matched_value} lines (max 300). LLM analyzed what doesn't belong.",
        fix_instruction="Remove or trim the sections flagged by the LLM response below.",
        llm_consequence=LLMConsequence(
            provider="skainet",
            model="zai-org/GLM-5.1-FP8",
            prompt="You are reviewing a README.md that exceeds 300 lines. Identify the specific sections that don't belong in a README and make it too long. For each section, explain why it should be removed or trimmed. Be concrete — reference section headings and line ranges. Common bloat: full install logs, API reference dumps, changelogs, verbose examples, duplicated content.",
            timeout=300,
        ),
    ),

    # ════════════════════════════════════════════════════════════════════
    # WARN — critical-component reminders. Block unless --confirm-read-warnings.
    # Fires when you touch files with broad blast radius. The reminder tells
    # you what to verify before acknowledging.
    # ════════════════════════════════════════════════════════════════════

    # ─── Reminder: core types changed — verify everything ───────────────
    Rule(
        id="verify-types-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="types.py changed")],
        file_globs=["enforcer/types.py"],
        message="Core types changed in {file}. Every matcher/predicate/combinator depends on these. Run full test suite: pytest --tb=short -q",
        fix_instruction="Verify: pytest passes, no matcher breaks on new types.py.",
        diff_only=True,
    ),

    # ─── Reminder: rule.py changed — verify glob matching + check() ──────
    Rule(
        id="verify-rule-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="rule.py changed")],
        file_globs=["enforcer/rule.py"],
        message="Rule/glob matching changed in {file}. _glob_match and Rule.check() affect every rule. Run: pytest tests/test_rule.py tests/test_runner.py",
        fix_instruction="Verify: glob matching works for ** patterns, Rule.check() stamps metadata correctly.",
        diff_only=True,
    ),

    # ─── Reminder: runner.py changed — verify finalizers + severity ──────
    Rule(
        id="verify-runner-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="runner.py changed")],
        file_globs=["enforcer/runner.py"],
        message="Runner changed in {file}. Cross-file finalizers and severity filtering affect all rules. Run: pytest tests/test_runner.py tests/test_metadata_rules.py",
        fix_instruction="Verify: run_cross_file_finalizers works, severity filtering correct, LLM consequences fire.",
        diff_only=True,
    ),

    # ─── Reminder: context.py changed — verify parse-once cache ──────────
    Rule(
        id="verify-context-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="context.py changed")],
        file_globs=["enforcer/context.py"],
        message="FileContextBuilder changed in {file}. Parse-once cache drives all AST matchers. Run: pytest tests/test_context.py tests/test_parse_once.py",
        fix_instruction="Verify: AST populated lazily, cache hits don't reparse, needs_for_file aggregates correctly.",
        diff_only=True,
    ),

    # ─── Reminder: config.py changed — verify load_config ───────────────
    Rule(
        id="verify-config-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="config.py changed")],
        file_globs=["enforcer/config.py"],
        message="Config loader changed in {file}. load_config executes enforcer_config.py as module. Run: pytest tests/test_config.py",
        fix_instruction="Verify: RULES/WORKSPACE/SEVERITY_ACTIONS/LLM_CONFIG extracted correctly, defaults work.",
        diff_only=True,
    ),

    # ─── Reminder: parser changed — verify AST for all languages ────────
    Rule(
        id="verify-parser-changed",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="parser changed")],
        file_globs=["enforcer/parsers/*.py"],
        message="Parser changed in {file}. Tree-sitter parse affects all AST matchers. Run: pytest tests/test_parsers.py tests/test_parse_once.py",
        fix_instruction="Verify: Python/TS/CSS ASTs parse correctly, language_for_path maps extensions right.",
        diff_only=True,
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}

LLM_CONFIG = {
    "concurrency": 3,
    "timeout": 45,
}
