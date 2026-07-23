"""Tests for EndpointAuthMatcher (ASP.NET minimal-API inline auth-guard enforcement)."""
import pytest
from enforcer.matchers.endpoint_auth import EndpointAuthMatcher
from enforcer.types import FileContext, Needs
from enforcer.parsers.tree_sitter import parse


def _run(body: str):
    """Wrap endpoint statements in a method body, parse, and run the matcher."""
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    src = f"class P {{ void Configure() {{ {body} }} }}\n"
    ctx = FileContext(path="Program.cs", raw=src, ast=parse(src, Needs.AST_CSHARP))
    return EndpointAuthMatcher().find(ctx)


@pytest.mark.parametrize("body", [
    'app.MapGet("/x", H);',
    'app.MapPost("/y", H);',
    'app.MapDelete("/d/{id}", H);',
    'app.MapGet("/x", H).WithName("z");',
])
def test_unguarded_endpoint_flags(body: str):
    """A Map* endpoint with no inline RequireAuthorization/AllowAnonymous is flagged."""
    matches = _run(body)
    assert matches
    assert matches[0].matched_value.startswith("Map")


@pytest.mark.parametrize("body", [
    'app.MapGet("/x", H).RequireAuthorization();',
    'app.MapPost("/y", H).AllowAnonymous();',
    'app.MapGet("/x", H).RequireAuthorization().WithName("z");',
    'app.UseRouting();',
    'svc.MapThing("/x", H);',
])
def test_guarded_or_non_endpoint_clean(body: str):
    """Inline-guarded endpoints, non-endpoint calls, and unknown Map* names are clean."""
    assert not _run(body)


def test_reports_endpoint_line():
    """The violation is attributed to the endpoint registration line."""
    matches = _run('app.MapGet("/x", H);')
    assert len(matches) == 1
    assert matches[0].line == 1


def test_multiple_endpoints_mixed():
    """Only the unguarded endpoint among several is flagged."""
    body = 'app.MapGet("/a", H).RequireAuthorization(); app.MapGet("/b", H);'
    matches = _run(body)
    assert len(matches) == 1
