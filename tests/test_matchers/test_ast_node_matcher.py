import pytest
from enforcer import FileContext
from enforcer.matchers import AstNodeMatcher

def test_ast_finds_literal_expressions():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = "const x = 42;\nconst y = 100;\n"
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = AstNodeMatcher(node_type="literal_expression")
    matches = matcher.find(ctx)
    assert len(matches) == 2
    assert matches[0].matched_value == "42"
    assert matches[1].matched_value == "100"

def test_ast_finds_by_line():
    try:
        import tree_sitter
        import tree_sitter_typescript
    except ImportError:
        pytest.skip("tree-sitter not installed")

    ts_code = "const x = 42;\n"
    from enforcer.parsers.tree_sitter import parse
    from enforcer.types import Needs
    tree = parse(ts_code, Needs.AST_TS)
    if tree is None:
        pytest.skip("tree-sitter TS grammar not available")

    ctx = FileContext(path="x.ts", raw=ts_code, ast=tree)
    matcher = AstNodeMatcher(node_type="literal_expression")
    matches = matcher.find(ctx)
    assert matches[0].line == 1
