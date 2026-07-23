"""Tests for AST predicates: HasDecoratorPredicate, NodeNamePredicate."""
import re
import pytest
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

def _decorator_match(source: str) -> Match:
    """Build a Match at the function declared in source, with AST context attached."""
    ctx = _make_ctx(source)
    func_node = _find_function(ctx.ast.root_node)
    match = Match(file="test.py", line=func_node.start_point[0] + 1)
    match.file_ctx = ctx
    return match


@pytest.mark.parametrize("source", [
    "@fixture\ndef f():\n    pass\n",
    "@app.route('/x')\ndef g():\n    pass\n",
    "@staticmethod\ndef h():\n    pass\n",
])
def test_has_decorator_passes_when_decorated(source):
    """HasDecoratorPredicate passes for any function carrying a decorator."""
    assert HasDecoratorPredicate().test(_decorator_match(source)) is True


@pytest.mark.parametrize("source", [
    "def a():\n    pass\n",
    "def b(x):\n    return x\n",
    "x = 1\ndef c():\n    pass\n",
])
def test_has_decorator_fails_when_undecorated(source):
    """HasDecoratorPredicate fails (no match) when the declaration has no decorator."""
    assert not HasDecoratorPredicate().test(_decorator_match(source))


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
    match.file_ctx = ctx  # ponytail: attach context for predicate to access AST
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
    match.file_ctx = ctx
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
    match.file_ctx = ctx
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
    match.file_ctx = ctx
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
    match.file_ctx = ctx
    pred = NodeNamePredicate(pattern=r"^test_")
    assert pred.test(match) is False

def test_predicate_without_ctx_returns_false():
    """Predicates should return False when no file_ctx attached (defensive)."""
    match = Match(file="test.py", line=1, matched_value="foo")
    assert HasDecoratorPredicate().test(match) is False
    assert NodeNamePredicate(pattern=r"foo").test(match) is False


def test_predicate_works_through_rule_check():
    """HasDecoratorPredicate should work when invoked through Rule.check()."""
    from enforcer.rule import Rule
    from enforcer.types import Severity
    from enforcer.matchers.naming_convention import NamingConventionMatcher

    source = (
        "@app.route('/api')\n"
        "def Bad_Name():\n"
        "    pass\n"
        "def good_name():\n"
        "    pass\n"
    )
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, Needs.AST_PY)

    rule = Rule(
        id="naming",
        severity=Severity.WARN,
        matchers=[NamingConventionMatcher(
            declaration_types=["function_definition"],
            pattern=r"^[a-z_][a-z0-9_]*$",
        )],
        file_globs=["*.py"],
        predicates=[HasDecoratorPredicate(pattern=r"app\.route")],
        message="Decorated function {matched_value} must be snake_case",
    )
    matches = rule.check(ctx, {})
    # Only Bad_Name has @app.route decorator — should be the only match
    assert len(matches) == 1
    assert "Bad_Name" in matches[0].matched_value
    assert "good_name" not in [m.matched_value for m in matches]
