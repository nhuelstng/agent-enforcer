"""Reflection seam over rules and matchers, shared by the doc and explain renderers.

Both `docs` and `explain` need the same two facts about a matcher: the labelled
sections of its docstring (What/Ignores/Basis/shared_ctx) and the path of its paired
test file. Owning them here removes the duplicated docstring parsing and the reach
into a private explain helper — renderers format this view, they don't re-derive it."""
from __future__ import annotations
import inspect
import re
from pathlib import Path

_SECTION_RE = re.compile(r'^\s*(What|Ignores|Basis|shared_ctx)\s*:\s*(.+)$', re.MULTILINE)


def parse_docstring_sections(doc: str | None) -> dict[str, str]:
    """Parse a matcher docstring into labelled sections (What/Ignores/Basis/shared_ctx).

    Returns {label: text}; missing sections are omitted. Each section is one line
    ('Label: value'); multi-line bodies are truncated to the first line by design."""
    if not doc:
        return {}
    return {m.group(1): m.group(2).strip() for m in _SECTION_RE.finditer(doc)}


def matcher_sections(matcher) -> dict[str, str]:
    """Return the docstring sections of a matcher instance (via its class docstring)."""
    return parse_docstring_sections(inspect.getdoc(matcher))


def _snake_case_class(class_name: str) -> str:
    """Convert CamelCase class name to snake_case: RegexMatcher -> regex_matcher."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', class_name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def paired_test(class_name: str, workspace: str) -> Path | None:
    """Locate the paired test file for a matcher class, or None.

    Tries tests/test_matchers/test_{snake}.py, then the same without the '_matcher'
    suffix. Returns the first existing path."""
    snake = _snake_case_class(class_name)
    candidates = [
        f"tests/test_matchers/test_{snake}.py",
        f"tests/test_matchers/test_{snake.replace('_matcher', '')}.py",
    ]
    for rel in candidates:
        p = Path(workspace) / rel
        if p.exists():
            return p
    return None
