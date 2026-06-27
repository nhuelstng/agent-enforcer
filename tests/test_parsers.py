from enforcer.types import Needs
from enforcer.parsers.language import language_for_path
from enforcer.parsers.tree_sitter import parse


def test_language_for_path_ts():
    assert language_for_path("foo.ts") == Needs.AST_TS


def test_language_for_path_py():
    assert language_for_path("foo.py") == Needs.AST_PY


def test_language_for_path_css():
    assert language_for_path("foo.css") == Needs.AST_CSS


def test_language_for_path_unknown():
    assert language_for_path("foo.txt") is None


def test_parse_returns_tree():
    src = "const x = 1;\n"
    tree = parse(src, Needs.AST_TS)
    if tree is None:
        # tree-sitter optional deps not installed in this env; skip gracefully
        import pytest
        pytest.skip("tree-sitter typescript not installed")
    assert tree is not None
    # tree-sitter Tree objects have a root_node attribute
    assert hasattr(tree, "root_node")
    assert tree.root_node is not None


if __name__ == "__main__":
    test_language_for_path_ts()
    test_language_for_path_py()
    test_language_for_path_css()
    test_language_for_path_unknown()
    print("ok")
