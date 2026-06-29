"""Test: run_cross_file_finalizers recurses into combinators to find finalize_duplicates."""
from dataclasses import dataclass, field
from enforcer import Severity, FileContext, Match
from enforcer.runner import RuleRunner
from enforcer.rule import Rule
from enforcer.combinators import AllOf


@dataclass
class FakeFinalizerMatcher:
    """Two-phase matcher stub: find() collects, finalize_duplicates() emits one match."""
    needs: object = None
    _emit: Match = field(default=None)

    def find(self, file_ctx, shared_ctx=None):
        return []

    def finalize_duplicates(self, shared_ctx):
        m = Match(file="x.py", line=1, matched_value="dup")
        return [m]


def test_finalizer_found_inside_combinator():
    matcher = FakeFinalizerMatcher()
    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[AllOf(matchers=[matcher])],
        file_globs=["**/*.py"],
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert len(matches) == 1
    assert matches[0].rule_id == "dup"
    assert matches[0].severity == Severity.ERROR


def test_finalizer_filters_by_file_globs():
    finalizer_match = Match(file="other/path.ts", line=1, matched_value="dup")

    class EmittingMatcher:
        needs = None

        def find(self, file_ctx, shared_ctx=None):
            return []

        def finalize_duplicates(self, shared_ctx):
            return [finalizer_match]

    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[EmittingMatcher()],
        file_globs=["src/**/*.py"],
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert matches == [], f"expected file_globs to filter out non-matching file, got {matches}"


def test_finalizer_filters_by_exclude_globs():
    finalizer_match = Match(file="src/vendor/dup.py", line=1, matched_value="dup")

    class EmittingMatcher:
        needs = None

        def find(self, file_ctx, shared_ctx=None):
            return []

        def finalize_duplicates(self, shared_ctx):
            return [finalizer_match]

    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[EmittingMatcher()],
        file_globs=["**/*.py"],
        exclude_globs=["src/vendor/**"],
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert matches == [], f"expected exclude_globs to filter out excluded file, got {matches}"


def test_finalizer_skips_diff_only_rules():
    class EmittingMatcher:
        needs = None

        def find(self, file_ctx, shared_ctx=None):
            return []

        def finalize_duplicates(self, shared_ctx):
            return [Match(file="src/x.py", line=1, matched_value="dup")]

    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[EmittingMatcher()],
        file_globs=["**/*.py"],
        diff_only=True,
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert matches == [], f"expected diff_only rule to skip finalizers, got {matches}"


def test_finalizer_applies_predicates():
    finalizer_match = Match(file="src/x.py", line=1, matched_value="dup")

    class EmittingMatcher:
        needs = None

        def find(self, file_ctx, shared_ctx=None):
            return []

        def finalize_duplicates(self, shared_ctx):
            return [finalizer_match]

    class RejectAllPredicate:
        def test(self, match: Match) -> bool:
            return False

    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[EmittingMatcher()],
        file_globs=["**/*.py"],
        predicates=[RejectAllPredicate()],
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert matches == [], f"expected predicate to filter out match, got {matches}"


def test_finalizer_dedup_same_matcher_twice():
    call_count = {"n": 0}

    class CountingFinalizerMatcher:
        needs = None

        def find(self, file_ctx, shared_ctx=None):
            return []

        def finalize_duplicates(self, shared_ctx):
            call_count["n"] += 1
            return [Match(file="src/x.py", line=1, matched_value="dup")]

    matcher = CountingFinalizerMatcher()
    rule = Rule(
        id="dup",
        severity=Severity.ERROR,
        matchers=[matcher, matcher],
        file_globs=["**/*.py"],
        message="dup found",
        fix_instruction="dedupe",
    )
    runner = RuleRunner([rule], workspace=".")
    matches = runner.run_cross_file_finalizers({})
    assert call_count["n"] == 1, f"expected finalize_duplicates called once, got {call_count['n']}"
    assert len(matches) == 1, f"expected one match, got {len(matches)}"
