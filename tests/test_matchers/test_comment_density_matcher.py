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
