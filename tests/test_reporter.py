import json
import pytest
from enforcer import Severity, Match
from enforcer.reporter import Reporter

def test_json_output_format():
    matches = [
        Match(file="x.ts", line=1, column=7, message="Raw hex", rule_id="no-raw-hex",
              severity=Severity.ERROR, fix_instruction="Use var(--color-*)"),
    ]
    output = Reporter(format="json").render(matches)
    data = json.loads(output)
    assert data["summary"]["total"] == 1
    assert data["summary"]["errors"] == 1
    assert data["issues"][0]["file"] == "x.ts"
    assert data["issues"][0]["line"] == 1
    assert data["issues"][0]["severity"] == "error"

def test_text_output_format():
    matches = [
        Match(file="x.ts", line=1, column=7, message="Raw hex", rule_id="no-raw-hex",
              severity=Severity.ERROR, fix_instruction="Use var(--color-*)"),
    ]
    output = Reporter(format="text").render(matches)
    assert "x.ts:1:7 [ERROR] no-raw-hex" in output
    assert "Raw hex" in output
    assert "Use var(--color-*)" in output

def test_json_with_llm_response():
    matches = [
        Match(file="README.md", line=0, message="Too long", rule_id="verbose-readme",
              severity=Severity.WARN, llm_response="Lines 45-80 are architecture details..."),
    ]
    output = Reporter(format="json").render(matches)
    data = json.loads(output)
    assert data["issues"][0]["llm_response"] == "Lines 45-80 are architecture details..."

def test_exit_code_no_errors():
    matches = [Match(file="x.ts", line=1, message="warn", severity=Severity.WARN)]
    assert Reporter().exit_code(matches) == 0

def test_exit_code_with_errors():
    matches = [Match(file="x.ts", line=1, message="err", severity=Severity.ERROR)]
    assert Reporter().exit_code(matches) == 1

def test_empty_json_output():
    output = Reporter(format="json").render([])
    data = json.loads(output)
    assert data["summary"]["total"] == 0
    assert data["issues"] == []

def test_text_empty_output():
    output = Reporter(format="text").render([])
    assert "No issues found" in output

def test_multiple_severities_sorted():
    matches = [
        Match(file="a.ts", line=1, message="info", severity=Severity.INFO, rule_id="r1"),
        Match(file="b.ts", line=1, message="error", severity=Severity.ERROR, rule_id="r2"),
        Match(file="c.ts", line=1, message="warn", severity=Severity.WARN, rule_id="r3"),
    ]
    output = Reporter(format="text").render(matches)
    error_pos = output.index("ERROR")
    warn_pos = output.index("WARN")
    info_pos = output.index("INFO")
    assert error_pos < warn_pos < info_pos

def test_json_summary_counts():
    matches = [
        Match(file="a.ts", line=1, severity=Severity.ERROR),
        Match(file="b.ts", line=1, severity=Severity.ERROR),
        Match(file="c.ts", line=1, severity=Severity.WARN),
        Match(file="d.ts", line=1, severity=Severity.INFO),
    ]
    data = json.loads(Reporter(format="json").render(matches))
    assert data["summary"]["total"] == 4
    assert data["summary"]["errors"] == 2
    assert data["summary"]["warnings"] == 1
    assert data["summary"]["info"] == 1
