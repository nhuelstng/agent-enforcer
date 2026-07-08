"""Tests for CssCustomPropertyDeclMatcher: governed token declaration-site detection."""
import pytest
from enforcer.matchers.css_custom_property import CssCustomPropertyDeclMatcher
from enforcer.types import FileContext, Needs

_PREFIXES = ("--color-", "--space-", "--radius-")


def _ctx(css_body: str, path: str = "src/app/x.component.scss") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    source = ":root {\n" + css_body + "\n}\n"
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_CSS)
    return ctx


@pytest.mark.parametrize("decl", [
    "--color-primary: #fff;",
    "--space-2: 8px;",
    "--radius-md: 6px;",
])
def test_flags_governed_token_declarations(decl):
    """Declaring a governed token custom property is flagged as a violation."""
    matches = CssCustomPropertyDeclMatcher(prefixes=_PREFIXES).find(_ctx(decl))
    assert len(matches) == 1


@pytest.mark.parametrize("decl", [
    "--my-local-thing: 4px;",
    "color: var(--color-primary);",
    "--z-index-modal: 1000;",
])
def test_clean_non_governed_declarations(decl):
    """Non-governed custom properties and token references are not flagged."""
    matches = CssCustomPropertyDeclMatcher(prefixes=_PREFIXES).find(_ctx(decl))
    assert not matches


def test_empty_prefixes_is_noop_clean():
    """With no prefixes configured the matcher flags nothing."""
    assert not CssCustomPropertyDeclMatcher().find(_ctx("--color-primary: #fff;"))


def test_no_ast_returns_empty_clean():
    """A file with no parsed AST yields no matches."""
    matcher = CssCustomPropertyDeclMatcher(prefixes=_PREFIXES)
    assert not matcher.find(FileContext(path="x.scss", raw=None))
