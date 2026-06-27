from enforcer.types import Match, Severity
from enforcer.reporter import Reporter


def _warn_match():
    return Match(file="style.css", line=1, rule_id="no-duplicate-css", severity=Severity.WARN, message="Check for duplicates.")


def _error_match():
    return Match(file="app.ts", line=5, rule_id="no-raw-hex", severity=Severity.ERROR, message="Raw hex.")


def test_warn_does_not_block_by_default():
    r = Reporter()
    assert r.exit_code([_warn_match()]) == 0


def test_warn_blocks_with_block_warn_action():
    r = Reporter()
    actions = {Severity.WARN: "block_warn"}
    assert r.exit_code([_warn_match()], severity_actions=actions) == 1


def test_warn_does_not_block_when_confirmed():
    r = Reporter()
    actions = {Severity.WARN: "block_warn"}
    assert r.exit_code([_warn_match()], severity_actions=actions, confirm_warnings=True) == 0


def test_error_still_blocks_even_when_confirmed():
    r = Reporter()
    assert r.exit_code([_error_match()], confirm_warnings=True) == 1


def test_text_output_shows_confirm_hint_when_warn_blocks():
    r = Reporter(format="text")
    actions = {Severity.WARN: "block_warn"}
    out = r.render([_warn_match()], severity_actions=actions)
    assert "ENFORCER_CONFIRM_WARNINGS=1" in out


def test_text_output_no_confirm_hint_when_warn_not_blocking():
    r = Reporter(format="text")
    out = r.render([_warn_match()])
    assert "ENFORCER_CONFIRM_WARNINGS" not in out
