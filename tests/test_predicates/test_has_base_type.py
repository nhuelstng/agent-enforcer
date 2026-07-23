"""Tests for HasBaseTypePredicate (base class / interface filtering)."""
import pytest
from enforcer.predicates.ast import HasBaseTypePredicate
from enforcer.types import Match, FileContext, Needs


def _match(source: str, node_type: str, lang: Needs) -> Match:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, lang)
    if tree is None:
        pytest.skip("tree-sitter grammar not available")
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


@pytest.mark.parametrize("source,pattern", [
    ("public class UsersController : ControllerBase { }\n", r"ControllerBase"),
    ("public class H : IRequestHandler { }\n", r"IRequestHandler"),
    ("public class R : BaseRepo, IRepo { }\n", r"IRepo"),
])
def test_has_base_type_present(source, pattern):
    """Passes when the class declares a base type matching the pattern."""
    assert HasBaseTypePredicate(pattern=pattern).test(
        _match(source, "class_declaration", Needs.AST_CSHARP))


@pytest.mark.parametrize("source,pattern", [
    ("public class Plain { }\n", r"ControllerBase"),
    ("public class UsersController : ControllerBase { }\n", r"DbContext"),
    ("public class R : IRepo { }\n", r"ControllerBase"),
])
def test_has_base_type_absent(source, pattern):
    """Does not pass when no base type matches the pattern."""
    assert not HasBaseTypePredicate(pattern=pattern).test(
        _match(source, "class_declaration", Needs.AST_CSHARP))


def test_no_pattern_matches_any_base():
    """With no pattern, any declared base type passes."""
    assert HasBaseTypePredicate().test(
        _match("public class C : Base { }\n", "class_declaration", Needs.AST_CSHARP))
    assert not HasBaseTypePredicate().test(
        _match("public class C { }\n", "class_declaration", Needs.AST_CSHARP))


def test_python_base_class():
    """Language-agnostic: a Python class argument_list is read too."""
    src = "class Repo(BaseRepo):\n    pass\n"
    assert HasBaseTypePredicate(pattern=r"BaseRepo").test(
        _match(src, "class_definition", Needs.AST_PY))
