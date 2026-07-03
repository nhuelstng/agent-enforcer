"""Tests for NoModuleSideEffectsMatcher: flags module-level statements causing side effects."""
import pytest
from enforcer.matchers.no_module_side_effects import NoModuleSideEffectsMatcher
from enforcer.types import FileContext, Needs


def _make_ctx(source: str, path: str = "x.py") -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    ctx = FileContext(path=path, raw=source)
    ctx.ast = parse(source, Needs.AST_PY)
    return ctx


_CLEAN = '''\
import os
from pathlib import Path

CONSTANT = 42

def foo():
    return 1

class Bar:
    pass
'''

_WITH_PRINT = '''\
import os
print("hello")
'''

_WITH_CALL = '''\
import os
register_plugin()
'''

_WITH_FOR = '''\
import os
for x in range(10):
    pass
'''

_CLEAN_IF = '''\
import sys
if sys.version_info < (3, 10):
    import importlib_metadata
'''


class TestNoModuleSideEffectsFlags:
    """flags module-level statements causing side effects."""

    @pytest.mark.parametrize("source,expected_type", [
        (_WITH_PRINT, "expression_statement"),
        (_WITH_FOR, "for_statement"),
    ])
    def test_flags_side_effect(self, source, expected_type):
        ctx = _make_ctx(source)
        matches = NoModuleSideEffectsMatcher().find(ctx)
        assert len(matches) >= 1
        assert any(m.matched_value == expected_type for m in matches)

    def test_flags_call_statement(self):
        ctx = _make_ctx(_WITH_CALL)
        matches = NoModuleSideEffectsMatcher().find(ctx)
        assert len(matches) == 1


class TestNoModuleSideEffectsClean:
    """does not flag allowed top-level statements."""

    @pytest.mark.parametrize("source", [
        _CLEAN,
        _CLEAN_IF,
    ])
    def test_no_match_on_valid(self, source):
        ctx = _make_ctx(source)
        assert NoModuleSideEffectsMatcher().find(ctx) == []

    def test_needs_ast_py(self):
        assert NoModuleSideEffectsMatcher().needs == Needs.AST_PY

    def test_no_ast_returns_empty(self):
        ctx = FileContext(path="x.py", raw="x = 1\n")
        assert NoModuleSideEffectsMatcher().find(ctx) == []
