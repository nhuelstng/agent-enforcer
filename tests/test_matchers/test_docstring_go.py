"""Go-language tests for DocstringMatcher (doc-comment presence on exported decls)."""
import pytest
from enforcer.matchers.docstring import DocstringMatcher
from enforcer.types import FileContext, Needs


def _go_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_GO)
    if tree is None:
        pytest.skip("tree-sitter go grammar not available")
    return FileContext(path="main.go", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "package main\nfunc Exported() {}\n",
    "package main\nfunc Handle() error { return nil }\n",
    "package main\nfunc (s *Server) Start() {}\n",
])
def test_go_missing_doc_flags(src):
    """Should flag exported Go declarations that lack a doc comment."""
    assert DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src))


@pytest.mark.parametrize("src", [
    "package main\n// Exported does a thing.\nfunc Exported() {}\n",
    "package main\n// Handle handles.\nfunc Handle() error { return nil }\n",
    "package main\n// Start begins serving.\nfunc (s *Server) Start() {}\n",
])
def test_go_documented_clean(src):
    """Should not flag exported Go declarations with an adjacent doc comment."""
    assert not DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src))


def test_go_unexported_skipped():
    """Unexported (lower-case) Go declarations are not required to have doc comments."""
    src = "package main\nfunc internalHelper() {}\nfunc (s *Server) doThing() {}\n"
    assert DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src)) == []


def test_go_blank_line_breaks_association():
    """A comment separated from the declaration by a blank line is not a doc comment."""
    src = "package main\n// orphan comment\n\nfunc Exported() {}\n"
    matches = DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src))
    assert len(matches) == 1
    assert matches[0].matched_value == "Exported"


def test_go_method_name_reported():
    """Method names (field_identifier) are extracted and reported."""
    src = "package main\nfunc (s *Server) Serve() {}\n"
    matches = DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src))
    assert matches[0].matched_value == "Serve"


def test_go_block_comment_counts():
    """A C-style /* */ comment directly above an exported func counts as documentation."""
    src = "package main\n/* Exported does a thing. */\nfunc Exported() {}\n"
    assert DocstringMatcher(needs=Needs.AST_GO).find(_go_ctx(src)) == []
