"""--all runs every rule, including diff_only ones, across the whole repo.

Regression guard: previously --all left changed_lines unset, so diff_only rules were
silently skipped and a full scan reported far fewer issues than it should."""
from enforcer.check_runner import run_checks, _all_line_numbers
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.rule import Rule
from enforcer.types import Severity, FileContext
from enforcer.matchers import RegexMatcher


def _diff_only_rule() -> Rule:
    return Rule(
        id="no-todo",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"TODO")],
        file_globs=["**/*.py"],
        diff_only=True,
    )


def _setup(tmp_path):
    (tmp_path / "a.py").write_text("x = 1  # TODO fix\n", encoding="utf-8")
    rule = _diff_only_rule()
    runner = RuleRunner([rule], workspace=str(tmp_path))
    builder = FileContextBuilder([rule], workspace=str(tmp_path))
    return runner, builder


def test_all_files_fires_diff_only_rule(tmp_path):
    """With all_files=True a diff_only rule fires across the whole file."""
    runner, builder = _setup(tmp_path)
    matches = run_checks(runner, builder, ["a.py"], {}, str(tmp_path),
                         staged=False, all_files=True)
    assert [m.rule_id for m in matches] == ["no-todo"]


def test_default_mode_suppresses_diff_only_rule(tmp_path):
    """Without staged/diff/all context a diff_only rule stays suppressed (unchanged behaviour)."""
    runner, builder = _setup(tmp_path)
    matches = run_checks(runner, builder, ["a.py"], {}, str(tmp_path), staged=False)
    assert matches == []


def test_all_line_numbers_covers_every_line():
    ctx = FileContext(path="x.py", raw="a\nb\nc\n")
    assert _all_line_numbers(ctx) == {1, 2, 3, 4}


def test_all_line_numbers_none_when_unreadable():
    assert _all_line_numbers(FileContext(path="x.bin", raw=None)) is None
