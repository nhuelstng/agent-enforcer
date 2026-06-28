"""Rule documentation generator: renders configured rules as markdown."""
from __future__ import annotations
from enforcer.rule import Rule
from enforcer.types import Severity

def render_rules_markdown(rules: list[Rule]) -> str:
    """Render configured rules as a markdown document."""
    if not rules:
        return "# Conventions\n\nNo rules configured.\n"

    sorted_rules = sorted(rules, key=lambda r: r.id)
    lines = ["# Conventions", ""]
    lines.append(f"_{len(sorted_rules)} rules configured._")
    lines.append("")

    for rule in sorted_rules:
        lines.append(f"## {rule.id}")
        lines.append("")
        lines.append(f"**Severity:** {rule.severity.value.upper()}")
        lines.append("")

        if rule.message:
            msg = "(dynamic)" if callable(rule.message) else rule.message
            lines.append(f"**Message:** {msg}")
            lines.append("")

        lines.append(f"**File globs:** {', '.join(rule.file_globs)}")
        lines.append("")

        if rule.exclude_globs:
            lines.append(f"**Excludes:** {', '.join(rule.exclude_globs)}")
            lines.append("")

        if rule.read_targets:
            lines.append(f"**Read targets:** {', '.join(rule.read_targets)}")
            lines.append("")

        if rule.fix_instruction:
            lines.append(f"**Fix:** {rule.fix_instruction}")
            lines.append("")

        if rule.llm_consequence:
            lines.append(f"**LLM check:** {rule.llm_consequence.prompt}")
            lines.append(f"**Model:** {rule.llm_consequence.model}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
