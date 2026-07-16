"""Go-language tests for AstNodeMatcher (scoped/typed node detection)."""
import pytest
from enforcer.matchers.ast_node import AstNodeMatcher
from enforcer.types import FileContext, Needs


def _go_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_GO)
    if tree is None:
        pytest.skip("tree-sitter go grammar not available")
    return FileContext(path="main.go", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "package main\nfunc init() {}\n",
    "package main\nfunc Run() {}\nfunc Stop() {}\n",
    "package main\nfunc a() {}\nfunc b() {}\nfunc c() {}\n",
])
def test_go_function_declaration_flags(src):
    """Should find Go function declarations by node type."""
    matcher = AstNodeMatcher(node_type="function_declaration", needs=Needs.AST_GO)
    assert matcher.find(_go_ctx(src))


@pytest.mark.parametrize("src", [
    "package main\nvar x = 1\n",
    "package main\nconst C = 2\n",
    "package main\ntype T struct{ a int }\n",
])
def test_go_function_declaration_clean(src):
    """Should not report function declarations in files that have none."""
    matcher = AstNodeMatcher(node_type="function_declaration", needs=Needs.AST_GO)
    assert not matcher.find(_go_ctx(src))


def test_go_finds_import_specs():
    """Each import within a Go import block is an import_spec node."""
    src = 'package main\nimport (\n    "fmt"\n    "os"\n)\n'
    matcher = AstNodeMatcher(node_type="import_spec", needs=Needs.AST_GO)
    assert len(matcher.find(_go_ctx(src))) == 2


def test_go_scope_limits_to_function_body():
    """A function scope restricts matching to nodes inside function bodies."""
    src = "package main\nvar top = 1\nfunc f() {\n    inner := 2\n}\n"
    matcher = AstNodeMatcher(node_type="short_var_declaration", scope="function", needs=Needs.AST_GO)
    matches = matcher.find(_go_ctx(src))
    assert len(matches) == 1
    assert "inner" in matches[0].matched_value
