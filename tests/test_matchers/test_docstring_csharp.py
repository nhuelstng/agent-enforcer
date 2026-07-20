"""C#-language tests for DocstringMatcher (XML doc-comment presence on public methods)."""
import pytest
from enforcer.matchers.docstring import DocstringMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="Widget.cs", raw=source, ast=tree)


def _wrap(members: str) -> str:
    return f"public class Widget\n{{\n{members}\n}}\n"


@pytest.mark.parametrize("member", [
    "    public void Build() { }",
    "    public int Compute(int a) { return a; }",
    "    // not a doc comment\n    public void Save() { }",
])
def test_csharp_missing_doc_flags(member):
    """Should flag public methods that lack a /// XML doc comment."""
    assert DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(_wrap(member)))


@pytest.mark.parametrize("member", [
    "    /// <summary>Builds it.</summary>\n    public void Build() { }",
    "    /// <summary>Computes.</summary>\n    public int Compute(int a) { return a; }",
    "    private void Helper() { }",
])
def test_csharp_documented_clean(member):
    """Should not flag documented public methods or non-public methods."""
    assert not DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(_wrap(member)))


def test_csharp_non_public_skipped():
    """private/protected methods are not required to carry doc comments."""
    src = _wrap("    private void Helper() { }\n    protected void Guard() { }")
    assert DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(src)) == []


def test_csharp_plain_comment_not_a_doc():
    """An ordinary // comment (not ///) does not document a public method."""
    src = _wrap("    // not a doc comment\n    public void Build() { }")
    matches = DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(src))
    assert len(matches) == 1
    assert matches[0].matched_value == "Build"


def test_csharp_blank_line_breaks_association():
    """A /// comment separated from the method by a blank line is not a doc comment."""
    src = _wrap("    /// <summary>orphan</summary>\n\n    public void Build() { }")
    matches = DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(src))
    assert len(matches) == 1
    assert matches[0].matched_value == "Build"


def test_csharp_method_name_reported_not_return_type():
    """The reported name is the method name, not its return type."""
    src = _wrap("    public Widget Make(string name) { return null; }")
    matches = DocstringMatcher(needs=Needs.AST_CSHARP).find(_cs_ctx(src))
    assert matches[0].matched_value == "Make"
