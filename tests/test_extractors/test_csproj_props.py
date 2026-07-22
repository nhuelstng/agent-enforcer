"""Tests for CsprojProps extractor (MSBuild property + PackageReference id extraction)."""
import pytest
from enforcer.extractors.csproj_props import CsprojProps


@pytest.mark.parametrize("raw,expected", [
    ("<Project><PropertyGroup><Nullable>enable</Nullable></PropertyGroup></Project>",
     {"Nullable"}),
    ("<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework>"
     "<TreatWarningsAsErrors>true</TreatWarningsAsErrors></PropertyGroup></Project>",
     {"TargetFramework", "TreatWarningsAsErrors"}),
    ('<Project><ItemGroup><PackageReference Include="Serilog" Version="3.0.0" />'
     '<PackageReference Update="xunit" /></ItemGroup></Project>',
     {"Serilog", "xunit"}),
])
def test_extract_extracts(raw, expected):
    """Property names and package ids are extracted."""
    result = CsprojProps().extract(raw)
    for key in expected:
        assert key in result


@pytest.mark.parametrize("raw", [
    "",
    "<Project></Project>",
    "not valid xml <<<",
])
def test_extract_absent(raw):
    """Empty, propertyless, or malformed input yields no keys."""
    assert not CsprojProps().extract(raw)


def test_strips_xml_namespace():
    """Classic non-SDK projects declare an xmlns; local names are still extracted."""
    raw = ('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
           "<PropertyGroup><LangVersion>latest</LangVersion></PropertyGroup></Project>")
    assert CsprojProps().extract(raw) == {"LangVersion"}


def test_combines_props_and_packages():
    """Properties and package ids merge into one key set."""
    raw = ('<Project><PropertyGroup><Nullable>enable</Nullable></PropertyGroup>'
           '<ItemGroup><PackageReference Include="Serilog" /></ItemGroup></Project>')
    assert CsprojProps().extract(raw) == {"Nullable", "Serilog"}
