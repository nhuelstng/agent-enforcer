"""Tests for AST predicates: HasDecoratorPredicate, NodeNamePredicate."""
import re
from enforcer.predicates.ast import HasDecoratorPredicate, NodeNamePredicate
from enforcer.types import Match, FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def _find_function(root):
    """Find first function_definition node, descending through decorated_definition."""
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "function_definition":
            return n
        stack.extend(reversed(n.children))
    return None

def test_has_decorator_predicate_pass():
    """HasDecoratorPredicate should pass when the match's node has a decorator."""
    source = (
        "@pytest.fixture\n"
        "def my_fixture():\n"
        "    return 42\n"
    )
    ctx = _make_ctx(source)
    # Find the function node and create a match at its location
    root = ctx.ast.root_node
    func_node = _find_function(root)
    assert func_node is not None
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="my_fixture",
    )
    match._file_ctx = ctx  # ponytail: attach context for predicate to access AST
    pred = HasDecoratorPredicate()
    assert pred.test(match) is True

def test_has_decorator_predicate_fail():
    """HasDecoratorPredicate should fail when no decorator."""
    source = "def no_decorator():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = _find_function(root)
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="no_decorator",
    )
    match._file_ctx = ctx
    pred = HasDecoratorPredicate()
    assert pred.test(match) is False

def test_has_decorator_with_pattern():
    """HasDecoratorPredicate should filter by decorator name pattern."""
    source = (
        "@app.route('/api')\n"
        "def endpoint():\n"
        "    pass\n"
    )
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = _find_function(root)
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="endpoint",
    )
    match._file_ctx = ctx
    pred = HasDecoratorPredicate(pattern=r"app\.route")
    assert pred.test(match) is True

    pred_no = HasDecoratorPredicate(pattern=r"pytest\.fixture")
    assert pred_no.test(match) is False

def test_node_name_predicate_match():
    """NodeNamePredicate should pass when node name matches pattern."""
    source = "def test_foo():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = _find_function(root)
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="test_foo",
    )
    match._file_ctx = ctx
    pred = NodeNamePredicate(pattern=r"^test_")
    assert pred.test(match) is True

def test_node_name_predicate_no_match():
    """NodeNamePredicate should fail when node name doesn't match."""
    source = "def not_a_test():\n    pass\n"
    ctx = _make_ctx(source)
    root = ctx.ast.root_node
    func_node = _find_function(root)
    match = Match(
        file="test.py",
        line=func_node.start_point[0] + 1,
        matched_value="not_a_test",
    )
    match._file_ctx = ctx
    pred = NodeNamePredicate(pattern=r"^test_")
    assert pred.test(match) is False

def test_predicate_without_ctx_returns_false():
    """Predicates should return False when no _file_ctx attached (defensive)."""
    match = Match(file="test.py", line=1, matched_value="foo")
    assert HasDecoratorPredicate().test(match) is False
    assert NodeNamePredicate(pattern=r"foo").test(match) is False
