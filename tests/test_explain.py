"""Tests for explain module: rule/matcher reflection and rendering."""
import pytest
from enforcer.explain import _parse_docstring_sections


class TestParseDocstringSectionsFound:
    """returns all four labeled sections when present."""

    @pytest.mark.parametrize("label", ["What", "Ignores", "Basis", "shared_ctx"])
    def test_section_present(self, label):
        doc = f"""First line summary.

        What:       flags lines matching pattern
        Ignores:    multiline patterns
        Basis:      RAW (regex on raw text)
        shared_ctx: none
        """
        sections = _parse_docstring_sections(doc)
        assert label in sections
        assert sections[label]  # non-empty

    @pytest.mark.parametrize("missing", ["Ignores", "Basis", "shared_ctx"])
    def test_missing_section_omitted(self, missing):
        doc = f"""Summary.

        What: flags lines
        """
        if missing != "What":
            doc = doc  # only What present
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
