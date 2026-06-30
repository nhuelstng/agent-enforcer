"""Explain module: reflects over configured rules and matcher docstrings to render explainers."""
from __future__ import annotations
import dataclasses
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
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


def _snake_case_class(class_name: str) -> str:
    """Convert CamelCase class name to snake_case: RegexMatcher -> regex_matcher."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', class_name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _find_paired_test(class_name: str, workspace: str) -> Path | None:
    """Locate the paired test file for a matcher class.

    Tries (in order): tests/test_matchers/test_{snake}.py, tests/test_matchers/test_{snake_without_matcher}.py.
    Returns Path of first existing match, or None.
    """
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


@dataclass
class WorkedExample:
    """A 4-line snippet from a paired test file, showing input -> match assertion."""
    test_class_name: str
    test_method_name: str
    snippet: str
    file_path: str
    line: int


def _name_of(node) -> str:
    """Return the identifier text of a class/function node, or empty string."""
    from enforcer.parsers.ast_utils import node_text
    for child in node.children:
        if child.type == "identifier":
            return node_text(child)
    return ""


def _snippet_for(node, lines: list[str], test_path: Path, class_name: str = "", method_name: str = "") -> WorkedExample:
    """Build a WorkedExample from a tree-sitter node (first 5 lines of its body)."""
    start_line = node.start_point[0]
    end_line = min(node.end_point[0] + 1, start_line + 5)
    snippet = "\n".join(lines[start_line:end_line])
    return WorkedExample(
        test_class_name=class_name,
        test_method_name=method_name,
        snippet=snippet,
        file_path=str(test_path),
        line=start_line + 1,
    )


def _find_test_class_example(root, lines: list[str], test_path: Path) -> WorkedExample | None:
    """Find first Test* class with its first method; return snippet or None."""
    from enforcer.parsers.ast_utils import walk_ast
    for node in walk_ast(root):
        if node.type != "class_definition":
            continue
        class_name = _name_of(node)
        if not class_name.startswith("Test"):
            continue
        for inner in walk_ast(node):
            if inner.type == "function_definition" and inner.start_point[0] > node.start_point[0] and inner.end_point[0] <= node.end_point[0]:
                return _snippet_for(inner, lines, test_path, class_name, _name_of(inner))
        return _snippet_for(node, lines, test_path, class_name)
    return None


def _find_module_test_example(root, lines: list[str], test_path: Path) -> WorkedExample | None:
    """Find first module-level test_ function; return snippet or None."""
    from enforcer.parsers.ast_utils import walk_ast
    for node in walk_ast(root):
        if node.type != "function_definition":
            continue
        name = _name_of(node)
        if name.startswith("test_"):
            return _snippet_for(node, lines, test_path, "(module-level)", name)
    return None


def _extract_worked_example(test_path: Path, matcher_class_name: str) -> WorkedExample | None:
    """Parse a test file via tree-sitter, return first test class+method or module-level test_ func snippet.

    Returns None if the file can't be parsed or has no test classes/methods.
    """
    try:
        source = test_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not source.strip():
        return None

    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs

    tree = parse(source, Needs.AST_PY)
    if tree is None:
        return None

    root = tree.root_node
    lines = source.splitlines()

    example = _find_test_class_example(root, lines, test_path)
    if example is not None:
        return example
    return _find_module_test_example(root, lines, test_path)
