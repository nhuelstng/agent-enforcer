"""Tests for FacadeExposesInterfaceMatcher: flags facade files with no interface declaration."""
import pytest
from enforcer.matchers.facade_exposes_interface import FacadeExposesInterfaceMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "__init__.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_PROTOCOL = '''\
from typing import Protocol

class Repo(Protocol):
    def find(self, id: int) -> dict: ...
'''

_ABC = '''\
from abc import ABC

class Repo(ABC):
    def find(self, id: int) -> dict: ...
    pass
'''

_IMPL_ONLY = '''\
class RepoImpl:
    def find(self, id: int) -> dict:
        return {}
'''

_EMPTY = "x = 1\n"

_PLAIN_CLASS = '''\
class Config:
    value = 1
'''

_REEXPORT = '''\
from .repo import Repo  # Protocol defined in repo.py, re-exported here
__all__ = ["Repo"]
'''

_REEXPORT_EMPTY = '''\
from .repo import Repo
__all__ = []
'''


class TestFacadeExposesInterfaceFlags:
    """flags facade files with no Protocol/ABC/interface."""

    @pytest.mark.parametrize("source", [_IMPL_ONLY, _EMPTY, _PLAIN_CLASS, _REEXPORT_EMPTY])
    def test_fail_flags_no_interface(self, source):
        ctx = _make_ctx(source)
        matcher = FacadeExposesInterfaceMatcher()
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert "no interface" in matches[0].matched_value


class TestFacadeExposesInterfaceClean:
    """does not flag facades with Protocol/ABC or valid re-export."""

    @pytest.mark.parametrize("source", [_PROTOCOL, _ABC])
    def test_success_clean_with_interface(self, source):
        ctx = _make_ctx(source)
        matcher = FacadeExposesInterfaceMatcher()
        assert matcher.find(ctx) == []

    @pytest.mark.parametrize("source", [_REEXPORT, _PROTOCOL, _ABC])
    def test_success_clean_with_reexport(self, source):
        ctx = _make_ctx(source)
        matcher = FacadeExposesInterfaceMatcher()
        assert matcher.find(ctx) == []

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="__init__.py", raw="x = 1\n")
        assert FacadeExposesInterfaceMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert FacadeExposesInterfaceMatcher().needs == Needs.AST_PY
