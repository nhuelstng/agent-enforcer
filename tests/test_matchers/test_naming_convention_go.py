"""Go-language tests for NamingConventionMatcher."""
import pytest
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.types import FileContext, Needs


def _go_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_GO)
    if tree is None:
        pytest.skip("tree-sitter go grammar not available")
    return FileContext(path="main.go", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "package main\nfunc badName() {}\n",
    "package main\nfunc alsoBad() {}\n",
    "package main\nfunc lowercase() {}\n",
])
def test_go_exported_func_flags(src):
    """Should flag Go functions whose names are not exported (PascalCase)."""
    matcher = NamingConventionMatcher(
        declaration_types=["function_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_GO,
    )
    assert matcher.find(_go_ctx(src))


@pytest.mark.parametrize("src", [
    "package main\nfunc NewServer() {}\n",
    "package main\nfunc Run() {}\n",
    "package main\nfunc Handle() {}\n",
])
def test_go_exported_func_clean(src):
    """Should not flag exported Go function names."""
    matcher = NamingConventionMatcher(
        declaration_types=["function_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_GO,
    )
    assert not matcher.find(_go_ctx(src))


def test_go_method_name_from_field_identifier():
    """Go method names live on a field_identifier, not a plain identifier."""
    src = "package main\nfunc (s *Server) doThing() {}\n"
    matcher = NamingConventionMatcher(
        declaration_types=["method_declaration"], pattern=r"^[A-Z]", needs=Needs.AST_GO,
    )
    matches = matcher.find(_go_ctx(src))
    assert len(matches) == 1
    assert matches[0].matched_value == "doThing"


def test_go_type_spec_naming():
    """Should flag a Go type declared with a non-PascalCase name."""
    src = "package main\ntype myType struct{ x int }\n"
    matcher = NamingConventionMatcher(
        declaration_types=["type_spec"], pattern=r"^[A-Z]", needs=Needs.AST_GO,
    )
    matches = matcher.find(_go_ctx(src))
    assert matches[0].matched_value == "myType"
