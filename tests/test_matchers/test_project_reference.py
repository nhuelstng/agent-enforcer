"""Tests for ProjectReferenceMatcher (.csproj layer-boundary enforcement)."""
import pytest
from enforcer.matchers.project_reference import ProjectReferenceMatcher
from enforcer.types import FileContext


def _csproj(*includes: str) -> str:
    """Build a minimal SDK-style project file referencing the given projects."""
    refs = "".join(f'    <ProjectReference Include="{inc}" />\n' for inc in includes)
    return (
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <ItemGroup>\n'
        f'{refs}'
        '  </ItemGroup>\n'
        '</Project>\n'
    )


def _ctx(path: str, raw: str | None) -> FileContext:
    return FileContext(path=path, raw=raw)


_LAYERS = {"domain": ["src/Domain/**"], "infra": ["src/Infra/**"], "api": ["src/Api/**"]}


def _matcher(**kw) -> ProjectReferenceMatcher:
    base = dict(layers=_LAYERS, forbid_implicit=True, allowed_edges=[])
    base.update(kw)
    return ProjectReferenceMatcher(**base)


@pytest.mark.parametrize("source,include,edge", [
    ("src/Domain/Domain.csproj", "..\\Infra\\Infra.csproj", "domain -> infra"),
    ("src/Domain/Domain.csproj", "../Infra/Infra.csproj", "domain -> infra"),
    ("src/Api/Api.csproj", "..\\Infra\\Infra.csproj", "api -> infra"),
    ("src/Api/Api.csproj", "..\\Domain\\Domain.csproj", "api -> domain"),
])
def test_forbidden_reference_flags(source: str, include: str, edge: str):
    """A project reference crossing a disallowed layer edge is flagged."""
    matches = _matcher().find(_ctx(source, _csproj(include)))
    assert matches
    assert matches[0].matched_value == edge


@pytest.mark.parametrize("matcher,source,raw", [
    (_matcher(allowed_edges=[("api", "infra")]),
     "src/Api/Api.csproj", _csproj("..\\Infra\\Infra.csproj")),
    (ProjectReferenceMatcher(layers={"domain": ["src/Domain/**", "src/Shared/**"]},
                             allowed_edges=[]),
     "src/Domain/Domain.csproj", _csproj("..\\Shared\\Shared.csproj")),
    (_matcher(), "tools/Gen/Gen.csproj", _csproj("..\\Infra\\Infra.csproj")),
    (_matcher(), "src/Domain/Domain.csproj", "<Project><oops"),
    (_matcher(), "src/Domain/Domain.csproj", None),
])
def test_clean_reference_success(matcher, source, raw):
    """Allowed edges, intra-layer refs, unmapped sources, and bad input raise no violation."""
    assert not matcher.find(_ctx(source, raw))


def test_line_attribution():
    """The violation is reported on the offending <ProjectReference> line."""
    matches = _matcher().find(_ctx("src/Domain/Domain.csproj",
                                   _csproj("..\\Infra\\Infra.csproj")))
    assert matches[0].line == 3


def test_forbidden_edges_mode():
    """With forbid_implicit=False, only edges in forbidden_edges are flagged."""
    raw = _csproj("..\\Infra\\Infra.csproj")
    hit = _matcher(forbid_implicit=False, forbidden_edges=[("domain", "infra")])
    assert hit.find(_ctx("src/Domain/Domain.csproj", raw))
    miss = _matcher(forbid_implicit=False, forbidden_edges=[("api", "infra")])
    assert not miss.find(_ctx("src/Domain/Domain.csproj", raw))


def test_multiple_references_only_forbidden_flagged():
    """Among several references, only the forbidden edge is flagged."""
    raw = _csproj("..\\Api\\Api.csproj", "..\\Infra\\Infra.csproj")
    matches = _matcher(allowed_edges=[("domain", "api")]).find(
        _ctx("src/Domain/Domain.csproj", raw))
    assert len(matches) == 1
    assert matches[0].matched_value == "domain -> infra"
    assert matches[0].line == 4
