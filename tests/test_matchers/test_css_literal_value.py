"""Tests for CssLiteralValueMatcher: design-property literal detection over the CSS AST."""
import pytest
from enforcer.matchers.css_literal_value import CssLiteralValueMatcher
from enforcer.types import FileContext, Needs


def _ctx(css_body: str, path: str = "src/app/x.component.scss") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    source = ".x {\n" + css_body + "\n}\n"
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_CSS)
    return ctx


# Inlined case lists (the coverage self-check counts inline list literals).
@pytest.mark.parametrize("decl", [
    "color: #fff;",
    "background-color: red;",
    "margin: 8px;",
    "border-radius: 4px;",
    "font-size: 14px;",
    "font-weight: 700;",
    "transition-timing-function: ease-in;",
])
def test_flags_literal_design_values(decl):
    """Every hardcoded design value should be flagged as a violation."""
    matches = CssLiteralValueMatcher().find(_ctx(decl))
    assert len(matches) == 1


@pytest.mark.parametrize("decl", [
    "color: var(--color-primary);",
    "margin: var(--space-2);",
    "border-radius: var(--radius-md);",
    "font-size: var(--font-size-md);",
    "color: inherit;",
    "display: flex;",
    "width: 240px;",
])
def test_clean_token_and_layout_values(decl):
    """Token references, safe keywords, and layout literals must not be flagged."""
    matches = CssLiteralValueMatcher().find(_ctx(decl))
    assert not matches


@pytest.mark.parametrize("categories,decl,expected", [
    ({"color"}, "margin: 8px;", 0),      # spacing not active -> ignored
    ({"spacing"}, "margin: 8px;", 1),    # spacing active -> flagged
    ({"spacing"}, "color: #fff;", 0),    # colour not active -> ignored
])
def test_categories_scope_which_properties_flag(categories, decl, expected):
    """Only properties in the active `categories` are inspected."""
    matches = CssLiteralValueMatcher(categories=frozenset(categories)).find(_ctx(decl))
    assert len(matches) == expected


def test_no_ast_returns_empty_clean():
    """A file with no parsed AST yields no matches."""
    assert not CssLiteralValueMatcher().find(FileContext(path="x.scss", raw=None))
