"""Tests for AsyncMethodMatcher (C# async void and Task-naming conventions)."""
import pytest
from enforcer.matchers.async_method import AsyncMethodMatcher
from enforcer.types import FileContext, Needs


def _cs_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_CSHARP)
    if tree is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    return FileContext(path="C.cs", raw=source, ast=tree)


def _cls(method: str) -> str:
    return f"public class C {{\n    {method}\n}}\n"


@pytest.mark.parametrize("method", [
    "public async void Fire() { }",
    "private async void OnTick() { }",
    "async void Handle() { }",
])
def test_async_void_flags(method):
    """`async void` methods are flagged."""
    matcher = AsyncMethodMatcher(check="no_async_void", needs=Needs.AST_CSHARP)
    assert matcher.find(_cs_ctx(_cls(method)))


@pytest.mark.parametrize("method", [
    "public async Task FireAsync() { }",
    "public void Fire() { }",
    "public async Task<int> GetAsync() { return 1; }",
])
def test_async_void_clean(method):
    """Async Task methods and plain void methods are not flagged."""
    matcher = AsyncMethodMatcher(check="no_async_void", needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(_cls(method)))


@pytest.mark.parametrize("method", [
    "public Task Save() { return null; }",
    "public async Task<int> GetItems() { return 1; }",
    "public ValueTask<bool> Check() { return default; }",
])
def test_task_suffix_flags(method):
    """Task-returning methods not named *Async are flagged."""
    matcher = AsyncMethodMatcher(check="task_suffix", needs=Needs.AST_CSHARP)
    assert matcher.find(_cs_ctx(_cls(method)))


@pytest.mark.parametrize("method", [
    "public Task SaveAsync() { return null; }",
    "public async Task<int> GetItemsAsync() { return 1; }",
    "public int Compute() { return 1; }",
])
def test_task_suffix_clean(method):
    """Correctly-suffixed or non-Task methods are not flagged."""
    matcher = AsyncMethodMatcher(check="task_suffix", needs=Needs.AST_CSHARP)
    assert not matcher.find(_cs_ctx(_cls(method)))
