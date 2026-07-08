"""Tests for the CSS AST navigation helpers (enforcer/parsers/css_utils.py)."""
import pytest
from enforcer.parsers.tree_sitter import parse
from enforcer.parsers.css_utils import iter_declarations, property_name, value_nodes, descendants
from enforcer.types import Needs


def _root(css: str):
    return parse(css, Needs.AST_CSS).root_node


@pytest.mark.parametrize("css,expected_props", [
    (".x { color: red; }", ["color"]),
    (".x { color: red; margin: 0; }", ["color", "margin"]),
    (":root { --a: 1; --b: 2; }", ["--a", "--b"]),
])
def test_iter_declarations_and_property_name(css, expected_props):
    """iter_declarations + property_name recover each declaration's property."""
    props = [property_name(d) for d in iter_declarations(_root(css))]
    assert props == expected_props


@pytest.mark.parametrize("css", [
    ".x { display: block; }",
    ".x { width: 100%; }",
    ".x { color: blue; }",
])
def test_value_nodes_present(css):
    """value_nodes returns the nodes after the ':' for a single declaration."""
    decl = next(iter_declarations(_root(css)))
    assert len(value_nodes(decl)) >= 1


@pytest.mark.parametrize("css,needle", [
    (".x { color: #fff; }", "color_value"),
    (".x { margin: 8px; }", "unit"),
    (".x { width: var(--w); }", "function_name"),
])
def test_descendants_finds_nested_node_types(css, needle):
    """descendants walks the full subtree so nested node types are reachable."""
    decl = next(iter_declarations(_root(css)))
    types = {n.type for v in value_nodes(decl) for n in descendants(v)}
    assert needle in types
