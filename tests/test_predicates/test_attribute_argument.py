"""Tests for AttributeArgumentPredicate (C# attribute-argument inspection)."""
import pytest
from enforcer.predicates.ast import AttributeArgumentPredicate
from enforcer.types import Match, FileContext, Needs


def _cs_match(source: str, node_type: str = "class_declaration") -> Match:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    ctx = FileContext(path="C.cs", raw=source, ast=tree)
    stack, node = [tree.root_node], None
    while stack:
        n = stack.pop()
        if n.type == node_type:
            node = n
            break
        stack.extend(reversed(n.children))
    assert node is not None
    m = Match(file="C.cs", line=node.start_point[0] + 1, matched_value="x")
    m.file_ctx = ctx
    return m


@pytest.mark.parametrize("source,attribute", [
    ('[Route("api/users")]\npublic class C { }\n', "Route"),
    ('[ApiVersion("1.0")]\npublic class C { }\n', "ApiVersion"),
    ("[ProducesResponseType(200)]\npublic class C { }\n", "ProducesResponseType"),
])
def test_attribute_argument_present(source, attribute):
    """Passes when the named attribute carries an argument."""
    assert AttributeArgumentPredicate(attribute=attribute).test(_cs_match(source))


@pytest.mark.parametrize("source,attribute", [
    ("[Route]\npublic class C { }\n", "Route"),            # no argument list
    ("[ApiController]\npublic class C { }\n", "ApiController"),
    ('[Route("api")]\npublic class C { }\n', "ApiVersion"),  # different attribute
])
def test_attribute_argument_absent(source, attribute):
    """Does not pass when the attribute is missing or has no arguments."""
    assert not AttributeArgumentPredicate(attribute=attribute).test(_cs_match(source))


@pytest.mark.parametrize("arg_pattern,present", [
    (r"Status200OK", True),
    (r"Status404NotFound", False),
    (r"StatusCodes", True),
])
def test_attribute_arg_pattern(arg_pattern, present):
    """Filters by argument-text pattern."""
    source = "[ProducesResponseType(StatusCodes.Status200OK)]\npublic class C { }\n"
    result = AttributeArgumentPredicate(
        attribute="ProducesResponseType", arg_pattern=arg_pattern).test(_cs_match(source))
    assert result is present


def test_without_ctx_returns_false():
    """Defensive: no attached context yields False."""
    assert not AttributeArgumentPredicate(attribute="Route").test(
        Match(file="C.cs", line=1, matched_value="x"))
