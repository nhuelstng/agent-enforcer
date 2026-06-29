"""Tests for enforcer.parsers.ast_utils: shared AST walker + node-type constants."""
from enforcer.parsers.ast_utils import (
    walk_ast,
    find_functions,
    node_text,
    FUNC_NODE_TYPES,
    DECL_NODE_TYPES,
    IMPORT_NODE_TYPES,
)


class FakeNode:
    """Minimal tree-sitter node stub: .children/.type/.text."""
    def __init__(self, type_: str, text: str = "", children: list | None = None):
        self.type = type_
        self.text = text.encode() if isinstance(text, str) else text
        self.children = children or []


def test_walk_ast_yields_root_then_descendants_dfs():
    """walk_ast yields root then all descendants in iterative DFS order."""
    leaf_a = FakeNode("number", text="1")
    leaf_b = FakeNode("number", text="2")
    mid = FakeNode("block", text="b", children=[leaf_a, leaf_b])
    root = FakeNode("program", text="p", children=[mid])
    visited = [n.type for n in walk_ast(root)]
    assert visited[0] == "program"
    assert "block" in visited
    assert "number" in visited
    assert len(visited) == 4


def test_walk_ast_iterative_no_recursion_error_on_deep_chain():
    """walk_ast must not raise RecursionError on a 1500-deep node chain."""
    depth = 1500
    node = FakeNode("leaf", text="x")
    for _ in range(depth):
        node = FakeNode("expr", text="e", children=[node])
    visited = list(walk_ast(node))
    assert len(visited) == depth + 1


def test_func_node_types_contents():
    """FUNC_NODE_TYPES contains the expected Python+TS function/method node types."""
    assert "function_definition" in FUNC_NODE_TYPES
    assert "function_declaration" in FUNC_NODE_TYPES
    assert "method_definition" in FUNC_NODE_TYPES
    assert "method_declaration" in FUNC_NODE_TYPES


def test_decl_node_types_contents():
    """DECL_NODE_TYPES contains function/class/variable declaration node types."""
    assert "function_definition" in DECL_NODE_TYPES
    assert "function_declaration" in DECL_NODE_TYPES
    assert "method_definition" in DECL_NODE_TYPES
    assert "method_declaration" in DECL_NODE_TYPES
    assert "class_definition" in DECL_NODE_TYPES
    assert "class_declaration" in DECL_NODE_TYPES
    assert "variable_declaration" in DECL_NODE_TYPES


def test_import_node_types_contents():
    """IMPORT_NODE_TYPES contains Python+TS import statement node types."""
    assert "import_statement" in IMPORT_NODE_TYPES
    assert "import_from_statement" in IMPORT_NODE_TYPES
    assert "import_declaration" in IMPORT_NODE_TYPES


def test_find_functions_returns_only_function_nodes():
    """find_functions yields only nodes whose type is in FUNC_NODE_TYPES."""
    func_a = FakeNode("function_definition", text="a")
    cls = FakeNode("class_definition", text="c")
    func_b = FakeNode("method_declaration", text="b")
    root = FakeNode("program", text="p", children=[func_a, cls, func_b])
    funcs = find_functions(root)
    types = {n.type for n in funcs}
    assert types == {"function_definition", "method_declaration"}


def test_find_functions_iterative_no_recursion_error():
    """find_functions must not raise RecursionError on a deep chain."""
    depth = 1500
    leaf_func = FakeNode("function_definition", text="deep")
    node = leaf_func
    for _ in range(depth):
        node = FakeNode("block", children=[node])
    funcs = find_functions(node)
    assert len(funcs) == 1
    assert funcs[0].type == "function_definition"


def test_node_text_decodes_bytes():
    """node_text decodes bytes to str."""
    n = FakeNode("x", text="hello")
    assert node_text(n) == "hello"


def test_node_text_passes_str_through():
    """node_text returns str unchanged."""
    class StrNode:
        text = "raw"
    assert node_text(StrNode()) == "raw"
