"""Tests for InterfaceMatcher: flags classes with >=min_methods and no base class."""
import pytest
from enforcer.matchers.interface_check import InterfaceMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_BIG_NO_BASE = '''\
class Service:
    def a(self):
        pass
    def b(self):
        pass
    def c(self):
        pass
    def d(self):
        pass
'''

_BIG_WITH_BASE = '''\
class Service(BaseService):
    def a(self):
        pass
    def b(self):
        pass
    def c(self):
        pass
    def d(self):
        pass
'''

_BIG_DATACLASS = '''\
from dataclasses import dataclass

@dataclass
class Config:
    x: int = 0
    def a(self): pass
    def b(self): pass
    def c(self): pass
    def d(self): pass
'''

_SMALL_NO_BASE = '''\
class Tiny:
    def a(self):
        pass
    def b(self):
        pass
'''

_BIG_INHERITS_PROTOCOL = '''\
class Repo(Protocol):
    def a(self): ...
    def b(self): ...
    def c(self): ...
    def d(self): ...
'''


_MANY_PRIVATE_ONE_PUBLIC = '''\
class Worker:
    def run(self):
        pass
    def _a(self):
        pass
    def _b(self):
        pass
    def _c(self):
        pass
    def __init__(self):
        pass
'''


class TestInterfaceMatcherFlags:
    """flags non-dataclass classes with >=min_methods and no base class."""

    @pytest.mark.parametrize("source", [
        _BIG_NO_BASE,
    ])
    def test_flags_big_class_no_base(self, source):
        ctx = _make_ctx(source)
        matches = InterfaceMatcher().find(ctx)
        assert len(matches) == 1
        assert matches[0].matched_value == "Service"

    @pytest.mark.parametrize("min_methods", [2, 3, 4])
    def test_flags_at_thresholds(self, min_methods):
        src = "class C:\n" + "\n".join(f"    def m{i}(self): pass" for i in range(min_methods)) + "\n"
        ctx = _make_ctx(src)
        matches = InterfaceMatcher(min_methods=min_methods).find(ctx)
        assert len(matches) == 1

    @pytest.mark.parametrize("source", [
        "class C:\n    def a(self): pass\n    def b(self): pass\n    def c(self): pass\n    def d(self): pass\n    def e(self): pass\n",
    ])
    def test_flags_five_methods(self, source):
        ctx = _make_ctx(source)
        assert len(InterfaceMatcher().find(ctx)) == 1


class TestInterfaceMatcherClean:
    """does not flag dataclass, small, or inheriting classes."""

    @pytest.mark.parametrize("source", [
        _BIG_WITH_BASE,
        _BIG_DATACLASS,
        _SMALL_NO_BASE,
        _BIG_INHERITS_PROTOCOL,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert InterfaceMatcher().find(ctx) == []

    @pytest.mark.parametrize("source", [
        _MANY_PRIVATE_ONE_PUBLIC,
        "class C:\n    def p(self): pass\n    def _a(self): pass\n    def _b(self): pass\n    def _c(self): pass\n    def _d(self): pass\n",
        "class C:\n    def __init__(self): pass\n    def _x(self): pass\n    def _y(self): pass\n    def _z(self): pass\n",
    ])
    def test_private_methods_do_not_count(self, source):
        """Private/dunder methods don't count toward the interface threshold."""
        assert InterfaceMatcher().find(_make_ctx(source)) == []

    def test_needs_ast_py(self):
        assert InterfaceMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="class C: pass\n")
        assert InterfaceMatcher().find(ctx) == []
