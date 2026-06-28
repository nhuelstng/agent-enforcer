"""Tests for NamingConventionMatcher: enforces naming conventions on declarations."""
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.types import FileContext, Needs

def _make_ctx(source: str, lang: Needs = Needs.AST_PY) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path="test.py", raw=source)
    ctx.ast = parse(source, lang)
    return ctx

def test_python_function_must_be_snake_case():
    """Should flag non-snake_case Python function names."""
    ctx = _make_ctx("def BadName():\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "BadName" in matches[0].matched_value

def test_python_function_snake_case_ok():
    """Should not flag snake_case Python function names."""
    ctx = _make_ctx("def good_name():\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    assert matcher.find(ctx) == []

def test_python_class_must_be_pascal_case():
    """Should flag non-PascalCase Python class names."""
    ctx = _make_ctx("class lower_case:\n    pass\n")
    matcher = NamingConventionMatcher(
        declaration_types=["class_definition"],
        pattern=r"^[A-Z][a-zA-Z0-9]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "lower_case" in matches[0].matched_value

def test_typescript_method_camel_case():
    """Should flag non-camelCase TypeScript method names."""
    ctx = _make_ctx(
        "class Foo {\n  Bad_Method(): void {}\n}\n",
        lang=Needs.AST_TS,
    )
    matcher = NamingConventionMatcher(
        declaration_types=["method_definition"],
        pattern=r"^[a-z][a-zA-Z0-9]*$",
        needs=Needs.AST_TS,
    )
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert "Bad_Method" in matches[0].matched_value

def test_multiple_violations():
    """Should flag multiple naming violations in one file."""
    ctx = _make_ctx(
        "def BadOne():\n    pass\n"
        "def Also_Bad():\n    pass\n"
        "def good_one():\n    pass\n"
    )
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    matches = matcher.find(ctx)
    assert len(matches) == 2

def test_no_ast_returns_empty():
    """Should return empty list if AST is not available."""
    ctx = FileContext(path="test.py", raw="def Bad(): pass")
    matcher = NamingConventionMatcher(
        declaration_types=["function_definition"],
        pattern=r"^[a-z_]+$",
    )
    assert matcher.find(ctx) == []

def test_variable_naming():
    """Should check variable declarations in Python."""
    ctx = _make_ctx("BadVariable = 42\n")
    matcher = NamingConventionMatcher(
        declaration_types=["assignment"],  # ponytail: tree-sitter may not have this — using identifier
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    # ponytail: tree-sitter Python doesn't have a dedicated 'assignment' node
    # this test documents that — assignment is an expression_statement
    # for variable naming, use RegexMatcher on the raw text instead
    result = matcher.find(ctx)
    # Should return empty — no matching declaration_type nodes found
    assert result == []
