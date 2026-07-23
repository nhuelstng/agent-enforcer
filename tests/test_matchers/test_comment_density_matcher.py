import pytest
from enforcer import FileContext
from enforcer.matchers import CommentPerFunctionMatcher

def test_comment_density_basic():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = """
function foo() {
    // comment 1
    // comment 2
    // comment 3
    // comment 4
    return 1;
}
function bar() {
    // only one
    return 2;
}
"""
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = CommentPerFunctionMatcher(max_comments=3)
    matches = matcher.find(ctx)
    # foo has 4 comments (>3), bar has 1 (<=3)
    assert len(matches) == 1


def _ts_tree(code):
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_typescript  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter not installed")
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")
    return tree


_C2 = "function f() {\n  // a\n  // b\n  return 1;\n}\n"
_C3 = "function g() {\n  // a\n  // b\n  // c\n  return 2;\n}\n"
_C4 = "function h() {\n  // a\n  // b\n  // c\n  // d\n  return 3;\n}\n"


@pytest.mark.parametrize("code", [_C2, _C3, _C4])
def test_comment_density_flags_violation(code):
    ctx = FileContext(path="x.ts", raw=code, ast=_ts_tree(code))
    assert CommentPerFunctionMatcher(max_comments=1).find(ctx)


_OK0 = "function f() {\n  return 1;\n}\n"
_OK1 = "function g() {\n  // a\n  return 2;\n}\n"
_OK2 = "function h() {\n  return 3;\n}\n"


@pytest.mark.parametrize("code", [_OK0, _OK1, _OK2])
def test_comment_density_passes_clean(code):
    ctx = FileContext(path="x.ts", raw=code, ast=_ts_tree(code))
    assert not CommentPerFunctionMatcher(max_comments=1).find(ctx)
