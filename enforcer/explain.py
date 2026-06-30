"""Explain module: reflects over configured rules and matcher docstrings to render explainers."""
from __future__ import annotations
import dataclasses
import inspect
import re
from dataclasses import dataclass
from typing import Any

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


@dataclass
class MatcherExplainer:
    """Reflected metadata for a single matcher instance, rendered by explain."""
    class_name: str
    docstring_sections: dict[str, str]
    configured_params: dict[str, Any]


def render_matcher_explainer(matcher) -> MatcherExplainer:
    """Reflect over a matcher instance: class name, docstring sections, configured (non-default) params."""
    cls = type(matcher)
    doc = inspect.getdoc(matcher)
    sections = _parse_docstring_sections(doc)

    configured: dict[str, Any] = {}
    if dataclasses.is_dataclass(matcher):
        # ponytail: include all dataclass fields; can't distinguish explicit-default from unset
        for f in dataclasses.fields(matcher):
            configured[f.name] = getattr(matcher, f.name)

    return MatcherExplainer(
        class_name=cls.__name__,
        docstring_sections=sections,
        configured_params=configured,
    )
