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
    LLMConfig,
    ProviderConfig,
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
    LLMMatcher,
    DocSyncMatcher,
    TestCoverageMatcher,
    InterfaceMatcher,
    DuplicateRuleIdMatcher,
    TypeHintMatcher,
    AllSortedMatcher,
    NoModuleSideEffectsMatcher,
    ConstantNamingMatcher,
    MagicNumberMatcher,
    ArchitectureMatcher,
    FacadeExistsMatcher,
    FacadeExposesInterfaceMatcher,
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
        matchers=[BranchNameMatcher(pattern=r"^(feature|fix|chore|docs|refactor)/")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Branch '{matched_value}' doesn't match required pattern: type/description",
        fix_instruction="Rename: git branch -m <type>/<description>",
        rationale="Branches encode intent; CI/greps depend on the type/ prefix to route checks and changelogs.",
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
        rationale="Conventional Commits enable automated changelog generation and semantic versioning. Unstructured messages break tooling.",
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
        rationale="Untested matchers ship false positives/negatives silently. Paired tests catch regressions before they reach users.",
    ),

    # ─── Test pairing: every predicate has a test ─────────────────────────
    Rule(
        id="predicate-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/predicates/*.py",
            derived_glob="tests/test_predicates/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/predicates/*.py"],
        exclude_globs=["enforcer/predicates/__init__.py"],
        message="No test file for predicate {file}. Every predicate needs paired tests.",
        fix_instruction="Create tests/test_predicates/test_{stem}.py",
        diff_only=True,
        rationale="Predicates filter matches; untested predicates can silently suppress real violations or let false ones through.",
    ),

    # ─── Test pairing: every combinator has a test ───────────────────────
    Rule(
        id="combinator-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/combinators/*.py",
            derived_glob="tests/test_combinators/test_{stem}*.py",
            exclude_stems=["__init__", "core"],
        )],
        file_globs=["enforcer/combinators/*.py"],
        exclude_globs=["enforcer/combinators/__init__.py"],
        message="No test file for combinator {file}. Every combinator needs paired tests.",
        fix_instruction="Create tests/test_combinators/test_{stem}.py",
        diff_only=True,
        rationale="Combinators compose matcher logic; untested combinators can invert or short-circuit the intended logic.",
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
        exclude_globs=["enforcer/__init__.py", "enforcer/matchers/**", "enforcer/predicates/**", "enforcer/combinators/**", "enforcer/parsers/**", "enforcer/extractors/**"],
        message="No test file for core module {file}.",
        fix_instruction="Create tests/test_{stem}.py",
        diff_only=True,
        rationale="Core modules (rule, runner, context, config) are load-bearing; untested core changes can break every rule.",
    ),

    # ─── Test pairing: every extractor has a test ──────────────────────
    Rule(
        id="extractor-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/extractors/*.py",
            derived_glob="tests/test_extractors/test_{stem}*.py",
            exclude_stems=["__init__"],
        )],
        file_globs=["enforcer/extractors/*.py"],
        exclude_globs=["enforcer/extractors/__init__.py"],
        message="Extractor {file} has no paired test. Create tests/test_extractors/test_{stem}*.py",
        fix_instruction="Add a test file covering happy path, empty/malformed input, and format-specific edge cases.",
        diff_only=True,
        rationale="Extractors are pure string transforms — trivial to test. Missing tests mean regressions in key extraction go unnoticed.",
    ),

    # ─── Docstring convention: matchers must declare What: and Basis: ────
    Rule(
        id="matcher-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py", "enforcer/matchers/test_coverage.py"],
        message="Matcher class at {file}:{line} docstring missing 'What:' or 'Basis:' section.",
        fix_instruction="Add 'What: <what it flags>' and 'Basis: <RAW|AST_PY|AST_TS|AST_CSS>' lines to the class docstring.",
        diff_only=True,
        rationale="Matchers without structured docstrings can't be explained by `enforcer explain`. The What:/Basis: sections are the minimum for self-documentation.",
    ),

    # ─── Test coverage: matchers must have positive+negative parametrized tests ──
    Rule(
        id="matcher-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_matchers/*.py"],
        exclude_globs=["tests/test_matchers/__init__.py", "tests/test_matchers/test_test_coverage.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_fail, assert on match list) and negative case (test_*_success, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Matchers enforce conventions; tests enforce matchers. Without both positive and negative parameterized cases, matcher regressions go undetected.",
    ),

    # ─── Test coverage: predicates must have positive+negative parametrized tests ──
    Rule(
        id="predicate-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_predicates/*.py"],
        exclude_globs=["tests/test_predicates/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_passes, assert True) and negative case (test_*_fails, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Predicates filter matches; untested predicates can silently suppress real violations or let false ones through.",
    ),

    # ─── Test coverage: combinators must have positive+negative parametrized tests ──
    Rule(
        id="combinator-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_combinators/*.py"],
        exclude_globs=["tests/test_combinators/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_matches, assert on match list) and negative case (test_*_no_match, assert not), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Combinators compose matcher logic; untested combinators can invert or short-circuit the intended logic.",
    ),

    # ─── Test coverage: extractors must have positive+negative parametrized tests ──
    Rule(
        id="extractor-test-positive-negative",
        severity=Severity.ERROR,
        matchers=[TestCoverageMatcher()],
        file_globs=["tests/test_extractors/*.py"],
        exclude_globs=["tests/test_extractors/__init__.py"],
        message="Test file {file} missing positive or negative parameterized coverage (>=3 cases each).",
        fix_instruction="Add a positive case (test_*_extracts, assert key in set) and negative case (test_*_absent, assert key not in set), each @pytest.mark.parametrize with >=3 examples.",
        diff_only=True,
        rationale="Extractors are pure string transforms; untested extractors silently break key extraction.",
    ),

    # ─── Docstring convention: predicates must declare What: and Basis: ──
    Rule(
        id="predicate-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/predicates/*.py"],
        exclude_globs=["enforcer/predicates/__init__.py"],
        message="Predicate class at {file}:{line} docstring missing 'What:' or 'Basis:' section.",
        fix_instruction="Add 'What: <what it passes>' and 'Basis: <RAW|AST_PY|AST_TS|AST_CSS>' lines to the class docstring.",
        diff_only=True,
        rationale="Predicates filter matches; structured docstrings explain what they pass and why.",
    ),

    # ─── Docstring convention: combinators must declare What: ────────────
    Rule(
        id="combinator-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/combinators/*.py"],
        exclude_globs=["enforcer/combinators/__init__.py"],
        message="Combinator class at {file}:{line} docstring missing 'What:' section.",
        fix_instruction="Add 'What: <what it composes>' to the class docstring.",
        diff_only=True,
        rationale="Combinators compose matcher logic; structured docstrings explain the composition.",
    ),

    # ─── Docstring convention: extractors must declare What: ────────────
    Rule(
        id="extractor-docstring-structured",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?s)class\s+\w+.*?\"\"\"(?:(?!What:).)*?\"\"\"", redact=False)],
        file_globs=["enforcer/extractors/*.py"],
        exclude_globs=["enforcer/extractors/__init__.py"],
        message="Extractor class at {file}:{line} docstring missing 'What:' section.",
        fix_instruction="Add 'What: <what it extracts>' to the class docstring.",
        diff_only=True,
        rationale="Extractors are pure transforms; structured docstrings explain what they extract.",
    ),

    # ─── Nesting depth: max 3 levels ────────────────────────────────────
    Rule(
        id="max-nesting-depth",
        severity=Severity.ERROR,
        matchers=[FunctionComplexityMatcher(metric="nesting", max_value=3)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Function at {file}:{line} has nesting depth {matched_value} (max 3). Flatten with early returns or extract helpers.",
        fix_instruction="Extract nested logic into helper functions or use early returns/guard clauses.",
        diff_only=True,
        rationale="Deep nesting is hard to read, test, and maintain. Guard clauses and extraction keep functions flat and scannable.",
    ),

    # ─── Interface: classes with >=4 methods must inherit a base class ──
    Rule(
        id="class-needs-interface",
        severity=Severity.ERROR,
        matchers=[InterfaceMatcher(min_methods=4)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py"],
        message="Class '{matched_value}' at {file}:{line} has >=4 methods but no base class. Inherit from Protocol/ABC or a base class.",
        fix_instruction="Add a base class (Protocol, ABC, or domain base) to the class definition.",
        diff_only=True,
        rationale="Classes with many methods and no interface are hard to mock, test in isolation, and substitute. An interface enables polymorphism and dependency injection.",
    ),

    # ─── Architecture: layer dependency direction ──────────────────────
    Rule(
        id="arch-layer-deps",
        severity=Severity.ERROR,
        matchers=[ArchitectureMatcher(
            layers={
                "types":      ["enforcer/types.py"],
                "rule":       ["enforcer/rule.py"],
                "core":       ["enforcer/runner.py", "enforcer/context.py",
                               "enforcer/config.py", "enforcer/check_runner.py"],
                "matchers":   ["enforcer/matchers/**/*.py"],
                "predicates": ["enforcer/predicates/**/*.py"],
                "combinators":["enforcer/combinators/**/*.py"],
                "extractors": ["enforcer/extractors/**/*.py"],
                "parsers":    ["enforcer/parsers/**/*.py"],
                "io":         ["enforcer/cli.py", "enforcer/mcp_server.py",
                               "enforcer/reporter.py", "enforcer/docs.py",
                               "enforcer/explain.py", "enforcer/fix.py",
                               "enforcer/ignore.py"],
            },
            allowed_edges=[
                ("matchers", "types"),
                ("matchers", "parsers"),
                ("matchers", "extractors"),
                ("predicates", "types"),
                ("combinators", "types"),
                ("combinators", "matchers"),
                ("extractors", "types"),
                ("core", "types"),
                ("core", "rule"),
                ("core", "parsers"),
                ("core", "matchers"),
                ("core", "combinators"),
                ("core", "extractors"),
                ("io", "types"),
                ("io", "rule"),
                ("io", "core"),
                ("io", "parsers"),
                ("io", "matchers"),
                ("io", "combinators"),
                ("io", "extractors"),
                ("parsers", "types"),
                ("rule", "types"),
                ("rule", "combinators"),
            ],
            forbid_implicit=True,
        )],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/__init__.py"],
        diff_only=False,
        message="Layer violation: {matched_value} at {file}:{line}",
        fix_instruction="Move shared logic down to a lower layer, or add the edge to allowed_edges if intentional.",
        rationale="Importing upward creates circular deps and prevents isolated testing. Layers: types < rule/parsers/matchers/predicates/combinators/extractors < core < io.",
    ),

    # ─── Architecture: no private cross-module imports ─────────────────
    Rule(
        id="no-private-cross-import",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.\S+\s+import\s+_\w+"])],
        file_globs=["enforcer/**/*.py"],
        message="Private import at {file}:{line}: importing _-prefixed names from other modules breaks encapsulation.",
        fix_instruction="Make the imported symbol public (remove _ prefix) or move the shared logic to a common module.",
        diff_only=True,
        rationale="Importing private symbols creates hidden coupling. If a module needs a _-prefixed name, it either belongs in a shared module or should be made public.",
    ),

    # ─── Architecture: import layer direction (matchers must not import up) ──
    Rule(
        id="matchers-no-import-runner-cli",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[
            r"from\s+enforcer\.runner\s+import",
            r"from\s+enforcer\.cli\s+import",
            r"from\s+enforcer\.mcp_server\s+import",
            r"from\s+enforcer\.reporter\s+import",
            r"from\s+enforcer\.fix\s+import",
            r"from\s+enforcer\.docs\s+import",
            r"from\s+enforcer\.explain\s+import",
            r"from\s+enforcer\.config\s+import",
        ])],
        file_globs=["enforcer/matchers/*.py"],
        exclude_globs=["enforcer/matchers/__init__.py"],
        message="Import layer violation at {file}:{line}: matchers must not import from runner/cli/mcp_server/reporter/fix/docs/explain/config.",
        fix_instruction="Move the shared logic down to types.py, a new low-level module, or pass the dependency as a parameter.",
        diff_only=True,
        rationale="Matchers are low-level building blocks. If they import from higher layers (runner, cli), they become impossible to reuse in isolation or test without pulling the entire stack.",
    ),

    # ─── Architecture: rule.py must not import from runner/cli ────────
    Rule(
        id="rule-no-import-up",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.runner\s+import", r"from\s+enforcer\.cli\s+import", r"from\s+enforcer\.mcp_server\s+import", r"from\s+enforcer\.reporter\s+import", r"from\s+enforcer\.fix\s+import", r"from\s+enforcer\.docs\s+import", r"from\s+enforcer\.explain\s+import", r"from\s+enforcer\.config\s+import"])],
        file_globs=["enforcer/rule.py"],
        message="Import layer violation at {file}:{line}: rule.py must not import from runner/cli/mcp_server/reporter/fix/docs/explain/config.",
        fix_instruction="Move the shared logic down to types.py or a new low-level module.",
        diff_only=True,
        rationale="rule.py defines Rule — the core unit of composition. Importing from runner or cli creates a circular dependency and prevents isolated testing.",
    ),

    # ─── Architecture: runner.py must not import from cli/mcp_server ──
    Rule(
        id="runner-no-import-cli",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"from\s+enforcer\.cli\s+import", r"from\s+enforcer\.mcp_server\s+import"])],
        file_globs=["enforcer/runner.py"],
        message="Import layer violation at {file}:{line}: runner.py must not import from cli or mcp_server.",
        fix_instruction="Move the shared logic to a mid-level module that both runner and cli can import.",
        diff_only=True,
        rationale="runner.py applies rules to files. Importing from cli or mcp_server (entrypoints) creates a circular dependency and prevents reuse.",
    ),

    # ─── Config hygiene: no duplicate rule IDs ─────────────────────────
    Rule(
        id="no-duplicate-rule-ids",
        severity=Severity.ERROR,
        matchers=[DuplicateRuleIdMatcher()],
        file_globs=["enforcer_config.py"],
        message="Duplicate Rule id '{matched_value}' in config. Each id must be unique.",
        fix_instruction="Rename one of the duplicate rules to a unique id.",
        rationale="Duplicate rule IDs silently shadow each other — one rule's config overwrites the other's in any id-keyed lookup.",
    ),

    # ─── Config hygiene: public functions must have return type hints ─
    Rule(
        id="public-function-return-type",
        severity=Severity.ERROR,
        matchers=[TypeHintMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py"],
        message="Function '{matched_value}' at {file}:{line} missing return type annotation.",
        fix_instruction="Add `-> ReturnType` to the function signature.",
        diff_only=True,
        rationale="Return type annotations document the contract and enable static analysis. Without them, callers must read the implementation to know what a function returns.",
    ),

    # ─── Module hygiene: __all__ must be alphabetically sorted ────────
    Rule(
        id="all-sorted",
        severity=Severity.ERROR,
        matchers=[AllSortedMatcher()],
        file_globs=["enforcer/**/*.py"],
        message="__all__ at {file}:{line} is not alphabetically sorted.",
        fix_instruction="Sort the __all__ entries alphabetically.",
        diff_only=True,
        rationale="Unsorted __all__ lists cause diff noise and make it hard to find exports. Alphabetical order is deterministic and scannable.",
    ),

    # ─── Module hygiene: no module-level side effects ─────────────────
    Rule(
        id="no-module-side-effects",
        severity=Severity.ERROR,
        matchers=[NoModuleSideEffectsMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py"],
        message="Module-level side effect at {file}:{line}: '{matched_value}' statement runs at import time.",
        fix_instruction="Move the side effect into a function or class method. Import-time execution breaks isolation and makes testing unpredictable.",
        diff_only=True,
        rationale="Module-level side effects (calls, loops, prints) run at import time, breaking isolation, making tests unpredictable, and causing import-order bugs.",
    ),

    # ─── Module hygiene: module-level constants must be UPPER_CASE ────
    Rule(
        id="constants-upper-case",
        severity=Severity.ERROR,
        matchers=[ConstantNamingMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py", "enforcer_config.py"],
        message="Module-level constant '{matched_value}' at {file}:{line} must be UPPER_CASE.",
        fix_instruction="Rename to UPPER_CASE or prefix with _ if private.",
        diff_only=True,
        rationale="UPPER_CASE constants are the Python convention (PEP 8). They distinguish compile-time-fixed values from mutable variables at a glance.",
    ),

    # ─── No magic numbers: integers outside -5..5 must be constants ────
    Rule(
        id="no-magic-numbers",
        severity=Severity.ERROR,
        matchers=[MagicNumberMatcher()],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer/mcp_server.py", "enforcer_config.py", "enforcer/types.py"],
        message="Magic number {matched_value} at {file}:{line}. Extract to a named constant.",
        fix_instruction="Assign to an UPPER_CASE constant: `MAX_VALUE = 42` then use `MAX_VALUE`.",
        diff_only=True,
        rationale="Magic numbers are unexplained literals. Without a name, their meaning is opaque. A named constant documents intent and centralizes change.",
    ),
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
        rationale="snake_case is the Python convention (PEP 8). Deviating creates inconsistency that makes code harder to scan.",
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
        rationale="CapWords (PascalCase) is the Python convention for classes (PEP 8). Distinguishes types from functions at a glance.",
    ),

    # ─── No print() in library code ──────────────────────────────────────
    Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found in library code at {file}:{line}. Use sys.stderr.write or structlog.",
        fix_instruction="Replace print() with sys.stderr.write(...).",
        rationale="print() writes to stdout, which is reserved for machine-readable output in CLI tools. Mixing human prose into stdout breaks piping and scripting. sys.stderr is the correct channel for human-facing diagnostics.",
    ),

    # ─── No bare except ─────────────────────────────────────────────────
    Rule(
        id="no-bare-except",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*except\s*:")],
        file_globs=["enforcer/**/*.py"],
        message="Bare except: at {file}:{line}. Use except Exception or more specific.",
        fix_instruction="Change to `except Exception:` or a more specific exception.",
        rationale="Bare except catches SystemExit and KeyboardInterrupt, masking intentional exits and making debugging impossible.",
    ),

    # ─── No secrets ─────────────────────────────────────────────────────
    Rule(
        id="no-secrets",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]", redact=True)],
        file_globs=["**/*.py"],
        exclude_globs=["**/test*", "**/*test*"],
        message="Possible hardcoded secret at {file}:{line}. Use env var.",
        fix_instruction="Move to env var or secrets manager.",
        rationale="Hardcoded secrets ship to the repo and can't be rotated without a commit. Env vars separate config from code and keep secrets out of version control.",
    ),

    # ─── No debug code (breakpoint/pdb) ─────────────────────────────────
    Rule(
        id="no-debug-code",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*(breakpoint\s*\(\s*\)|import\s+pdb|pdb\.set_trace\s*\()")],
        file_globs=["**/*.py"],
        exclude_globs=["**/test*", "**/*test*"],
        message="Debug code at {file}:{line}. Remove before commit.",
        fix_instruction="Remove breakpoint()/pdb.set_trace() or wrap in `if DEBUG:` guard.",
        rationale="Debug code left in production halts execution and blocks CI. A single forgotten breakpoint can page someone at 3am.",
    ),

    # ─── No type:ignore without reason ─────────────────────────────────
    Rule(
        id="no-bare-type-ignore",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#\s*type:\s*ignore\s*$")],
        file_globs=["**/*.py"],
        message="Bare `# type: ignore` at {file}:{line} silences errors without explanation.",
        fix_instruction="Add a reason: `# type: ignore[<error-code>]  # <why>`",
        diff_only=True,
        rationale="Bare `# type: ignore` hides real type errors and spreads — future readers can't tell if the ignore is still needed. A reason forces the author to justify the suppression.",
    ),

    # ─── File length limit ─────────────────────────────────────────────
    Rule(
        id="file-max-lines",
        severity=Severity.ERROR,
        matchers=[LineCountMatcher(max_lines=400)],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/cli.py", "enforcer_config.py"],
        message="File {file} has {matched_value} lines (max 400). Split into modules.",
        fix_instruction="Extract cohesive functionality into a new module or sub-package.",
        diff_only=True,
        rationale="Files over 400 lines do too much and are hard to navigate. Splitting into focused modules improves readability and testability.",
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
        rationale="Long functions do too much and are hard to test, read, and review. Splitting forces single-responsibility and improves testability.",
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
        rationale="More than 5 params signals the function does too much; group into a dataclass to make the boundary explicit and the call site readable.",
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
        rationale="High cyclomatic complexity means too many branches — hard to reason about, test, and maintain. Extract branches into helpers or use early returns.",
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
        rationale="Wildcard imports pollute the namespace and hide dependencies. Explicit imports make it clear where symbols come from and avoid name collisions.",
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
        rationale="TODOs without owners never get done. An owner reference makes responsibility explicit and enables grepping for open work.",
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
        rationale="Public functions are the API surface. Without docstrings, users (and agents) must read the implementation to understand intent — that's a failure of the contract.",
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
            prompt="You are reviewing a README.md that exceeds 300 lines. Identify the specific sections that don't belong in a README and make it too long. For each section, explain why it should be removed or trimmed. Be concrete — reference section headings and line ranges. Common bloat: full install logs, API reference dumps, changelogs, verbose examples, duplicated content.",
            timeout=300,
        ),
        rationale="A README over 300 lines is too long for a landing doc. Bloat hides the getting-started path; details belong in docs/.",
    ),

    # ─── Commit message aligns with changes (LLM sanity check) ──────────
    Rule(
        id="commit-msg-aligns-with-changes",
        severity=Severity.WARN,
        matchers=[LLMMatcher(
            prompt="Given the commit message and the modified file list, does the message accurately describe these changes? Lenient — sanity check only, not a full audit.",
            timeout=30,
        )],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="Commit message may not align with changes. LLM: {matched_value}",
        fix_instruction="Rewrite commit message to describe the actual changes.",
        rationale="A commit message that doesn't describe the actual changes misleads future archaeologists using git log/blame. The LLM sanity check catches gross mismatches.",
    ),

    # ─── Facade pattern: every submodule has a facade (__init__.py) ──────
    Rule(
        id="facade-exists",
        severity=Severity.WARN,
        matchers=[FacadeExistsMatcher(
            source_glob="enforcer/*",
            facade="__init__.py",
            workspace=".",
        )],
        file_globs=["enforcer/**/*.py"],
        exclude_globs=["enforcer/__init__.py"],
        diff_only=False,
        message="Submodule {file} has no facade (__init__.py)",
        fix_instruction="Create enforcer/{file}/__init__.py re-exporting the public API.",
        rationale="Every submodule should have a facade (__init__.py) that re-exports its public API. This enables clean imports and hides internal structure.",
    ),

    # ─── Facade pattern: facades expose an interface (Protocol/ABC or __all__) ──
    Rule(
        id="facade-exposes-interface",
        severity=Severity.WARN,
        matchers=[FacadeExposesInterfaceMatcher()],
        file_globs=["enforcer/*/__init__.py"],
        diff_only=False,
        message="Facade {file} exposes no interface (Protocol/ABC or __all__)",
        fix_instruction="Add a Protocol/ABC class or __all__ re-export to the facade.",
        rationale="Facades should expose a public interface (Protocol/ABC) or at minimum an __all__ re-export. This documents the contract and enables dependency injection.",
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
        rationale="types.py is load-bearing — every matcher, predicate, and combinator depends on it. Changes here can break the entire rule engine silently.",
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
        rationale="rule.py contains _glob_match and Rule.check() — every rule flows through it. Changes here affect glob matching and metadata stamping for all rules.",
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
        rationale="runner.py drives severity filtering, LLM consequence execution, and cross-file finalizers. Changes here can silently change which rules fire.",
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
        rationale="context.py owns the parse-once cache. A broken cache means every AST matcher re-parses or gets stale ASTs.",
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
        rationale="config.py executes enforcer_config.py as a module. Changes here affect how every rule is loaded.",
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
        rationale="The tree-sitter parser feeds all AST matchers. Changes here can silently break AST detection for Python, TS, or CSS.",
    ),

    # ─── Self-enforcement: CONVENTIONS.md in sync ────────────────────────
    Rule(
        id="conventions-md-stale",
        severity=Severity.ERROR,
        matchers=[DocSyncMatcher(doc_path="CONVENTIONS.md")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
        message="CONVENTIONS.md is stale or missing. Regenerate after changing rules.",
        fix_instruction="Run: enforcer sync-doc",
        rationale="A stale conventions doc misleads agents — they follow rules that no longer match the actual config. The doc must be regenerated whenever RULES changes, and direct edits to CONVENTIONS.md must not drift it from the config.",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}

LLM_CONFIG = LLMConfig(
    default_provider="custom",
    default_model="zai-org/GLM-5.1-FP8",
    concurrency=3,
    timeout=45,
    # Provider overrides/additions go here. Built-ins: custom, openai, anthropic, ollama, groq, mistral, deepseek.
    # See enforcer/llm.py DEFAULT_PROVIDERS for defaults. Override base_url, token_env, headers as needed.
    # providers={
    #     "my-private-llm": ProviderConfig(base_url="https://llm.internal/v1", token_env="LLM_TOKEN", headers={"Authorization": "Bearer {token}"}),
    # },
)
