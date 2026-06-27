import json
from enforcer.reporter import Reporter
from enforcer.types import Match, Severity


def test_sarif_empty():
    reporter = Reporter(format="sarif")
    output = reporter.render([])
    data = json.loads(output)
    assert data["version"] == "2.1.0"
    assert data["runs"][0]["results"] == []


def test_sarif_with_results():
    matches = [
        Match(
            file="src/app.ts",
            line=10,
            column=5,
            rule_id="no-raw-hex",
            severity=Severity.ERROR,
            message="Raw hex found",
            matched_value="#fff",
            fix_instruction="Use var(--color-*)",
        ),
    ]
    reporter = Reporter(format="sarif")
    output = reporter.render(matches)
    data = json.loads(output)
    assert data["version"] == "2.1.0"
    run = data["runs"][0]
    result = run["results"][0]
    assert result["ruleId"] == "no-raw-hex"
    assert result["level"] == "error"
    assert result["message"]["text"] == "Raw hex found"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "src/app.ts"
    assert loc["region"]["startLine"] == 10
    assert loc["region"]["startColumn"] == 5


def test_sarif_includes_rules_metadata():
    matches = [
        Match(
            file="x.ts", line=1, rule_id="test-rule",
            severity=Severity.WARN, message="test",
        ),
    ]
    reporter = Reporter(format="sarif")
    output = reporter.render(matches)
    data = json.loads(output)
    rules = data["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) == 1
    assert rules[0]["id"] == "test-rule"


def test_sarif_warn_level():
    matches = [
        Match(file="x.ts", line=1, rule_id="w", severity=Severity.WARN, message="w"),
    ]
    reporter = Reporter(format="sarif")
    data = json.loads(reporter.render(matches))
    assert data["runs"][0]["results"][0]["level"] == "warning"


def test_sarif_info_level():
    matches = [
        Match(file="x.ts", line=1, rule_id="i", severity=Severity.INFO, message="i"),
    ]
    reporter = Reporter(format="sarif")
    data = json.loads(reporter.render(matches))
    assert data["runs"][0]["results"][0]["level"] == "note"
