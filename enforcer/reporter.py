from __future__ import annotations
import json
from enforcer.types import Match, Severity

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}

class Reporter:
    def __init__(self, format: str = "text"):
        self.format = format

    def render(self, matches: list[Match]) -> str:
        if self.format == "json":
            return self._render_json(matches)
        return self._render_text(matches)

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

    def _render_text(self, matches: list[Match]) -> str:
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
        blocked = " Commit blocked." if summary["errors"] > 0 else ""
        lines.append(f"Summary: {summary['total']} issues ({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info).{blocked}")
        return "\n".join(lines) + "\n"

    def _summary(self, matches: list[Match]) -> dict:
        return {
            "total": len(matches),
            "errors": sum(1 for m in matches if m.severity == Severity.ERROR),
            "warnings": sum(1 for m in matches if m.severity == Severity.WARN),
            "info": sum(1 for m in matches if m.severity == Severity.INFO),
        }

    def exit_code(self, matches: list[Match]) -> int:
        return 1 if any(m.severity == Severity.ERROR for m in matches) else 0
