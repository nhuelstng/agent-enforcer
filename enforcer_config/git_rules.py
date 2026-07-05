"""Git metadata rules: branch naming and commit message format."""
from enforcer import Rule, Severity, RuleType
from enforcer.matchers import BranchNameMatcher, CommitMessageMatcher

GIT_RULES = [
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
]
