"""C#-language tests for InterfaceMatcher (classes needing a base type/interface)."""
import pytest
from enforcer.matchers.interface_check import InterfaceMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="C.cs", raw=source, ast=tree)


def _service(name: str, base: str, methods: int) -> str:
    body = "\n".join(f"    public void M{i}() {{ }}" for i in range(methods))
    return f"public class {name}{base} {{\n{body}\n}}\n"


@pytest.mark.parametrize("methods", [4, 5, 6])
def test_csharp_no_base_flags(methods):
    """A class with enough public methods and no base type is flagged."""
    matcher = InterfaceMatcher(min_methods=4, needs=Needs.AST_CSHARP)
    matches = matcher.find(_cs_ctx(_service("Service", "", methods)))
    assert matches
    assert matches[0].matched_value == "Service"


@pytest.mark.parametrize("source", [
    _service("Service", " : IService", 5),          # implements an interface
    _service("Service", " : BaseService", 5),        # inherits a base class
    _service("Small", "", 2),                        # below the method threshold
])
def test_csharp_clean(source):
    """A base type or too-few methods raises no violation."""
    matcher = InterfaceMatcher(min_methods=4, needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(source))


@pytest.mark.parametrize("source", [
    "public class C {\n    private void A() { }\n    private void B() { }\n"
    "    private void D() { }\n    private void E() { }\n}\n",
    "public class C {\n    void A() { }\n    void B() { }\n    void D() { }\n    void E() { }\n}\n",
    "public record R(int A, int B, int C, int D, int E);\n",
])
def test_csharp_non_public_and_records_clean(source):
    """Non-public methods don't count, and records (data carriers) are ignored."""
    matcher = InterfaceMatcher(min_methods=4, needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(source))
