"""Tests for HasAttributePredicate (C# [Attribute] filtering)."""
import pytest
from enforcer.predicates.ast import HasAttributePredicate
from enforcer.types import Match, FileContext, Needs


def _cs_match(source: str, node_type: str) -> Match:
    """Parse C#, find the first node of node_type, return a Match at its line with ctx attached."""
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    ctx = FileContext(path="C.cs", raw=source, ast=tree)
    stack = [tree.root_node]
    node = None
    while stack:
        n = stack.pop()
        if n.type == node_type:
            node = n
            break
        stack.extend(reversed(n.children))
    assert node is not None
    match = Match(file="C.cs", line=node.start_point[0] + 1, matched_value="x")
    match._file_ctx = ctx
    return match


@pytest.mark.parametrize("source,node_type", [
    ("[ApiController]\npublic class C : ControllerBase { }\n", "class_declaration"),
    ("public class C {\n    [HttpGet]\n    public void Get() { }\n}\n", "method_declaration"),
    ("[Serializable]\n[Obsolete]\npublic class C { }\n", "class_declaration"),
])
def test_has_attribute_present(source, node_type):
    """Passes when the declaration carries any attribute."""
    assert HasAttributePredicate().test(_cs_match(source, node_type)) is True


@pytest.mark.parametrize("source,node_type", [
    ("public class C : ControllerBase { }\n", "class_declaration"),
    ("public class C {\n    public void Get() { }\n}\n", "method_declaration"),
    ("public class C {\n    private int x;\n}\n", "class_declaration"),
])
def test_has_attribute_absent(source, node_type):
    """Does not pass when the declaration carries no attribute."""
    assert not HasAttributePredicate().test(_cs_match(source, node_type))


@pytest.mark.parametrize("pattern,present", [
    (r"ApiController", True),
    (r"Authorize", False),
    (r"Route", True),
])
def test_has_attribute_pattern(pattern, present):
    """Filters by attribute-text pattern."""
    source = '[ApiController]\n[Route("api")]\npublic class C { }\n'
    match = _cs_match(source, "class_declaration")
    assert HasAttributePredicate(pattern=pattern).test(match) is present


def test_class_attribute_not_attributed_to_inner_method():
    """An attribute on the enclosing class must not pass for an undecorated method."""
    source = "[ApiController]\npublic class C {\n    public void Get() { }\n}\n"
    match = _cs_match(source, "method_declaration")
    assert not HasAttributePredicate().test(match)


def test_without_ctx_returns_false():
    """Defensive: no attached context yields False."""
    assert not HasAttributePredicate().test(Match(file="C.cs", line=1, matched_value="x"))
