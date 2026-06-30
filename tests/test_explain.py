"""Tests for explain module: rule/matcher reflection and rendering."""
import inspect
from dataclasses import is_dataclass
import pytest
from pathlib import Path
from enforcer.matchers import RegexMatcher
from enforcer.explain import (
    _parse_docstring_sections,
    MatcherExplainer,
    render_matcher_explainer,
    _find_paired_test,
    _extract_worked_example,
    WorkedExample,
)


class TestParseDocstringSectionsFound:
    """returns all four labeled sections when present."""

    @pytest.mark.parametrize("label,expected", [
        ("What", "flags lines matching pattern"),
        ("Ignores", "multiline patterns"),
        ("Basis", "RAW (regex on raw text)"),
        ("shared_ctx", "none"),
    ])
    def test_section_present(self, label, expected):
        doc = f"""First line summary.

        What:       flags lines matching pattern
        Ignores:    multiline patterns
        Basis:      RAW (regex on raw text)
        shared_ctx: none
        """
        sections = _parse_docstring_sections(doc)
        assert label in sections
        assert sections[label] == expected

    @pytest.mark.parametrize("missing", ["Ignores", "Basis", "shared_ctx"])
    def test_missing_section_omitted(self, missing):
        doc = """Summary.

        What: flags lines
        """
        sections = _parse_docstring_sections(doc)
        assert missing not in sections
        assert "What" in sections


class TestParseDocstringSectionsClean:
    """handles edge cases without crashing."""

    @pytest.mark.parametrize("doc", [
        "",                          # empty
        "No sections here.",         # summary only
        "What: only one section",    # single section, no newline
        None,                        # None input
    ])
    def test_no_crash(self, doc):
        sections = _parse_docstring_sections(doc)
        assert isinstance(sections, dict)


class TestRenderMatcherExplainerFound:
    """renders class name, docstring sections, and configured params for a matcher."""

    @pytest.mark.parametrize("pattern,redact", [
        (r"^\s*print\s*\(", False),
        (r"password\s*=", True),
        (r"TODO", False),
    ])
    def test_renders_class_name_and_pattern(self, pattern, redact):
        matcher = RegexMatcher(pattern=pattern, redact=redact)
        explainer = render_matcher_explainer(matcher)
        assert explainer.class_name == "RegexMatcher"
        assert explainer.configured_params["pattern"] == pattern
        assert explainer.configured_params["redact"] == redact

    def test_renders_docstring_sections(self):
        matcher = RegexMatcher(pattern=r"print")
        explainer = render_matcher_explainer(matcher)
        # RegexMatcher will have its docstring retrofitted in Task 9;
        # until then the explainer should still return a dict (possibly empty)
        assert isinstance(explainer.docstring_sections, dict)

    def test_explainer_is_dataclass(self):
        assert is_dataclass(MatcherExplainer)


class TestRenderMatcherExplainerClean:
    """handles matchers with minimal or missing docstrings gracefully."""

    @pytest.mark.parametrize("matcher_factory", [
        lambda: RegexMatcher(pattern="x"),
    ])
    def test_no_crash_on_minimal_docstring(self, matcher_factory):
        explainer = render_matcher_explainer(matcher_factory())
        assert explainer.class_name  # always has a name
        assert isinstance(explainer.docstring_sections, dict)
        assert isinstance(explainer.configured_params, dict)


class TestFindPairedTestFound:
    """locates the paired test file for a matcher class."""

    @pytest.mark.parametrize("class_name,expected_file", [
        ("RegexMatcher", "test_regex_matcher.py"),     # preferred long form
        ("ImportMatcher", "test_import_matcher.py"),
        ("DocstringMatcher", "test_docstring.py"),     # falls back to existing short form
    ])
    def test_finds_test_file(self, class_name, expected_file):
        workspace = str(Path(__file__).resolve().parent.parent)  # repo root
        result = _find_paired_test(class_name, workspace)
        assert result is not None
        assert result.name in (expected_file, expected_file.replace("_matcher", ""))


class TestFindPairedTestClean:
    """returns None when no paired test file exists."""

    @pytest.mark.parametrize("class_name", [
        "NonexistentMatcher",       # no such matcher
        "TotallyFake",              # garbage
        "",                         # empty
    ])
    def test_returns_none_when_missing(self, class_name):
        result = _find_paired_test(class_name, str(Path(__file__).resolve().parent.parent))
        assert result is None


class TestExtractWorkedExampleFound:
    """extracts a 4-line worked example from a paired test file."""

    @pytest.mark.parametrize("matcher_class", [
        "RegexMatcher",
        "ImportMatcher",
    ])
    def test_returns_example_for_real_test_file(self, matcher_class):
        workspace = str(Path(__file__).resolve().parent.parent)
        test_path = _find_paired_test(matcher_class, workspace)
        assert test_path is not None
        example = _extract_worked_example(test_path, matcher_class)
        assert example is not None
        assert example.test_class_name  # non-empty
        assert example.test_method_name  # non-empty
        assert example.snippet  # non-empty source lines

    def test_worked_example_is_dataclass(self):
        assert is_dataclass(WorkedExample)


class TestExtractWorkedExampleClean:
    """returns None when test file can't be parsed or has no test classes."""

    @pytest.mark.parametrize("content", [
        "",                              # empty file
        "no tests here",                 # no test class
        "# just a comment",              # no test class
    ])
    def test_returns_none_on_no_tests(self, content, tmp_path):
        test_file = tmp_path / "test_fake.py"
        test_file.write_text(content)
        result = _extract_worked_example(test_file, "FakeMatcher")
        assert result is None
