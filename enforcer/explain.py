"""Explain module: reflects over configured rules and matcher docstrings to render explainers."""
from __future__ import annotations
import re

_SECTION_RE = re.compile(r'^\s*(What|Ignores|Basis|shared_ctx)\s*:\s*(.+)$', re.MULTILINE)


def _parse_docstring_sections(doc: str | None) -> dict[str, str]:
    """Parse a matcher class docstring into labeled sections (What/Ignores/Basis/shared_ctx).

    Returns dict mapping section label -> text. Missing sections omitted.
    Each section is single-line: 'Label: value' on one line. Multi-line section bodies
    are truncated to the first line (by design — the docstring convention is one-line sections).
    """
    if not doc:
        return {}
    return {m.group(1): m.group(2).strip() for m in _SECTION_RE.finditer(doc)}
