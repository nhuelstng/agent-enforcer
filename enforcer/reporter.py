"""Output formatter: text, JSON, and SARIF. Computes exit code from matches and severity actions."""
from __future__ import annotations
import json
from enforcer.types import Match, Severity

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}

class Reporter:
    """Renders match results in text, JSON, or SARIF format. Computes exit code based on severity actions."""
    def __init__(self, format: str = "text"):
        self.format = format

    def render(self, matches: list[Match], severity_actions: dict | None = None) -> str:
        """Format matches according to self.format (text/json/sarif)."""
        if self.format == "json":
            return self._render_json(matches)
        if self.format == "sarif":
            return self._render_sarif(matches)
        return self._render_text(matches, severity_actions)

    def _render_sarif(self, matches: list[Match]) -> str:
        _SEV_TO_SARIF = {Severity.ERROR: "error", Severity.WARN: "warning", Severity.INFO: "note"}
        results = []
        rules_seen = {}
        for m in matches:
            if m.rule_id not in rules_seen:
                rules_seen[m.rule_id] = {
                    "id": m.rule_id,
                    "name": m.rule_id,
                    "shortDescription": {"text": m.message or m.rule_id},
                    "defaultConfiguration": {"level": _SEV_TO_SARIF.get(m.severity, "note")},
                }
            results.append({
                "ruleId": m.rule_id,
                "level": _SEV_TO_SARIF.get(m.severity, "note"),
                "message": {"text": m.message},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": m.file},
                        "region": {"startLine": m.line, "startColumn": max(m.column, 1)},
                    }
                }],
            })
        sarif = {
            "version": "2.1.0",
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/Schemata/sarif-schema-2.1.0.json",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "pre-commit-agent-enforcer",
                        "rules": list(rules_seen.values()),
                    }
                },
                "results": results,
            }],
        }
        return json.dumps(sarif, indent=2)

    def _render_json(self, matches: list[Match]) -> str:
        summary = self._summary(matches)
        issues = []
        for m in sorted(matches, key=lambda m: (_SEVERITY_ORDER.get(m.severity, 99), m.file, m.line)):
            issue = {
                "file": m.file,
                "line": m.line,
                "column": m.column,
                "rule_id": m.rule_id,
                "severity": m.severity.value,
                "message": m.message,
                "matched_value": m.matched_value,
                "fix_instruction": m.fix_instruction,
                "llm_response": m.llm_response,
            }
            issues.append(issue)
        return json.dumps({"summary": summary, "issues": issues}, indent=2)

    def _render_text(self, matches: list[Match], severity_actions: dict | None = None) -> str:
        if not matches:
            return "No issues found.\n"
        lines = []
        sorted_matches = sorted(matches, key=lambda m: (_SEVERITY_ORDER.get(m.severity, 99), m.file, m.line))
        for m in sorted_matches:
            sev = m.severity.value.upper()
            loc = f"{m.file}:{m.line}"
            if m.column:
                loc += f":{m.column}"
            lines.append(f"{loc} [{sev}] {m.rule_id}")
            lines.append(f"  {m.message}")
            if m.fix_instruction:
                lines.append(f"  Fix: {m.fix_instruction}")
            if m.llm_response:
                lines.append(f"  LLM: {m.llm_response}")
            lines.append("")
        summary = self._summary(matches)
        actions = severity_actions or {}
        warnings_block = any(actions.get(m.severity) == "block_warn" and m.severity == Severity.WARN for m in matches)
        errors_block = summary["errors"] > 0
        if errors_block:
            lines.append(f"Summary: {summary['total']} issues ({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info). Commit blocked.")
        elif warnings_block:
            lines.append(f"Summary: {summary['total']} issues ({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info). Commit blocked (warnings require confirmation).")
            lines.append("Acknowledge warnings and retry: ENFORCER_CONFIRM_WARNINGS=1 git commit ...")
        else:
            lines.append(f"Summary: {summary['total']} issues ({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info).")
        return "\n".join(lines) + "\n"

    def _summary(self, matches: list[Match]) -> dict:
        return {
            "total": len(matches),
            "errors": sum(1 for m in matches if m.severity == Severity.ERROR),
            "warnings": sum(1 for m in matches if m.severity == Severity.WARN),
            "info": sum(1 for m in matches if m.severity == Severity.INFO),
        }

    def exit_code(self, matches: list[Match], severity_actions: dict | None = None, confirm_warnings: bool = False) -> int:
        """Return 1 if any match triggers a blocking action (block or block_warn). If confirm_warnings=True, only ERROR blocks."""
        if confirm_warnings:
            return 1 if any(m.severity == Severity.ERROR for m in matches) else 0
        actions = severity_actions or {Severity.ERROR: "block", Severity.WARN: "print", Severity.INFO: "hint"}
        for m in matches:
            action = actions.get(m.severity, "print")
            if action in ("block", "block_warn"):
                return 1
        return 0
