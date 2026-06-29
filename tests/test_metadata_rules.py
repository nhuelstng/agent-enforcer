"""Tests for metadata rule dispatch (branch/commit rules)."""
from pathlib import Path
from enforcer.types import Severity, RuleType, Match
from enforcer.rule import Rule
from enforcer.matchers.always import AlwaysMatcher

def test_rule_has_rule_type_field():
    """Rule should have a rule_type field defaulting to CONTENT."""
    r = Rule(id="x", severity=Severity.WARN, matchers=[AlwaysMatcher()], file_globs=["*"])
    assert r.rule_type == RuleType.CONTENT

def test_rule_can_be_metadata_type():
    """Rule should accept rule_type=RuleType.METADATA."""
    r = Rule(id="branch", severity=Severity.ERROR, matchers=[AlwaysMatcher()],
             file_globs=["*"], rule_type=RuleType.METADATA)
    assert r.rule_type == RuleType.METADATA

def test_runner_separates_metadata_rules():
    """RuleRunner should separate metadata rules from content rules."""
    from enforcer.runner import RuleRunner
    content_rule = Rule(id="c", severity=Severity.WARN, matchers=[AlwaysMatcher()], file_globs=["*.py"])
    meta_rule = Rule(id="m", severity=Severity.ERROR, matchers=[AlwaysMatcher()],
                     file_globs=["*"], rule_type=RuleType.METADATA)
    runner = RuleRunner([content_rule, meta_rule], workspace=".", no_llm=True)
    assert content_rule in runner.content_rules
    assert meta_rule in runner.metadata_rules

def test_runner_runs_metadata_rules_once():
    """Runner should run metadata rules once, not per-file."""
    from enforcer.runner import RuleRunner
    from enforcer.types import FileContext
    from enforcer.matchers.regex import RegexMatcher
    import subprocess, tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)
        os.makedirs(os.path.join(tmpdir, ".git/refs/heads"), exist_ok=True)
        Path(tmpdir, ".git/HEAD").write_text("ref: refs/heads/feature/test-123\n")
        Path(tmpdir, ".git/refs/heads/feature").mkdir(parents=True, exist_ok=True)
        Path(tmpdir, ".git/refs/heads/feature/test-123").write_text("0" * 40)

        meta_rule = Rule(
            id="branch-needs-ticket",
            severity=Severity.ERROR,
            matchers=[AlwaysMatcher(matched_value="bad branch")],
            file_globs=["*"],
            rule_type=RuleType.METADATA,
        )
        runner = RuleRunner([meta_rule], workspace=tmpdir, no_llm=True)
        ctx = FileContext(path="foo.py", raw="x = 1")
        matches = runner.run_rules_for_file(ctx, {})
        # Metadata rule should NOT fire during per-file run
        assert matches == []
        # Metadata rules fire via run_metadata_rules()
        meta_matches = runner.run_metadata_rules({})
        assert len(meta_matches) == 1


def test_metadata_sentinel_does_not_false_match_regex():
    """RegexMatcher with a common pattern must not false-match the runner's metadata sentinel."""
    from enforcer.runner import RuleRunner
    from enforcer.matchers.regex import RegexMatcher
    meta_rule = Rule(
        id="no-false-metadata",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(pattern=r"password\s*=")],
        file_globs=["*"],
        rule_type=RuleType.METADATA,
    )
    runner = RuleRunner([meta_rule], workspace=".", no_llm=True)
    matches = runner.run_metadata_rules({})
    assert matches == []


def test_commit_msg_alignment_rule_exists():
    """enforcer_config.py should have a commit-msg-aligns-with-changes rule."""
    import sys
    sys.path.insert(0, ".")
    import enforcer_config
    rule_ids = [r.id for r in enforcer_config.RULES]
    assert "commit-msg-aligns-with-changes" in rule_ids


def test_commit_msg_alignment_rule_uses_llm_matcher():
    """The rule should use an LLMMatcher."""
    import sys
    sys.path.insert(0, ".")
    import enforcer_config
    from enforcer.matchers.llm_check import LLMMatcher
    rule = next(r for r in enforcer_config.RULES if r.id == "commit-msg-aligns-with-changes")
    assert isinstance(rule.matchers[0], LLMMatcher)


def test_commit_msg_alignment_rule_is_metadata_type():
    """The rule should be METADATA type (runs once, not per-file)."""
    import sys
    sys.path.insert(0, ".")
    import enforcer_config
    from enforcer.types import RuleType
    rule = next(r for r in enforcer_config.RULES if r.id == "commit-msg-aligns-with-changes")
    assert rule.rule_type == RuleType.METADATA
