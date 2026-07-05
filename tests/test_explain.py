"""Tests for explain module: rule/matcher reflection and rendering."""
import inspect
import json
from dataclasses import is_dataclass
import pytest
from pathlib import Path
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
from enforcer.explain import (
    _parse_docstring_sections,
    MatcherExplainer,
    render_matcher_explainer,
    render_rule_explainer,
    render_rule_explainer_json,
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


def _sample_rule() -> Rule:
    return Rule(
        id="no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["enforcer/**/*.py"],
        message="print() found in library code at {file}:{line}.",
        fix_instruction="Replace print() with sys.stderr.write(...).",
        rationale="print() writes to stdout.",
        diff_only=True,
    )


class TestRenderRuleExplainerFound:
    """renders the full rule explainer text for a real rule."""

    @pytest.mark.parametrize("field", [
        "Rule: no-print",
        "Severity: ERROR",
        "Applies to: enforcer/**/*.py",
        "Matchers (1):",
        "RegexMatcher",
        "What:",
        "Basis:",
        "Worked example",
    ])
    def test_contains_field(self, field):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=str(Path(__file__).resolve().parent.parent))
        assert field in text

    def test_includes_diff_only_note(self):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=".")
        assert "Diff-only" in text or "diff_only" in text.lower() or "changed lines" in text.lower()

    def test_includes_message_and_fix(self):
        rule = _sample_rule()
        text = render_rule_explainer(rule, workspace=".")
        assert "print() found" in text
        assert "sys.stderr.write" in text


class TestRenderRuleExplainerClean:
    """handles rules with empty matchers or missing fields."""

    @pytest.mark.parametrize("matchers", [
        [],  # empty matchers list
    ])
    def test_no_crash_on_empty_matchers(self, matchers):
        rule = Rule(id="empty", severity=Severity.INFO, matchers=matchers, file_globs=["*.py"], message="m")
        text = render_rule_explainer(rule, workspace=".")
        assert "Rule: empty" in text
        assert "Matchers (0):" in text


class TestRenderRuleExplainerJsonFound:
    """returns a JSON-serializable dict with rule metadata and matcher details."""

    @pytest.mark.parametrize("key", [
        "rule_id", "severity", "file_globs", "diff_only", "message",
        "fix_instruction", "rationale", "matchers",
    ])
    def test_has_key(self, key):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        assert key in data

    def test_matchers_list_has_class_name(self):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        assert len(data["matchers"]) == 1
        assert data["matchers"][0]["class_name"] == "RegexMatcher"

    def test_json_serializable(self):
        rule = _sample_rule()
        data = render_rule_explainer_json(rule, workspace=".")
        # must not raise
        json.dumps(data)


class TestRenderRuleExplainerJsonClean:
    """handles rules with no matchers."""

    def test_empty_matchers_list(self):
        rule = Rule(id="empty", severity=Severity.INFO, matchers=[], file_globs=["*.py"], message="m")
        data = render_rule_explainer_json(rule, workspace=".")
        assert data["matchers"] == []


from enforcer.explain import load_rule_for_explain, ExplainResult


class TestLoadRuleForExplainFound:
    """finds a rule by exact id match."""

    @pytest.mark.parametrize("rule_id,expected_found", [
        ("no-raw-hex", True),
        ("max-lines-readme", False),
        ("nonexistent-rule", False),
    ])
    def test_finds_or_not(self, rule_id, expected_found, tmp_path):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-raw-hex", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")], file_globs=["*.ts"], message="m"),
]
WORKSPACE = "."
''')
        result = load_rule_for_explain(str(cfg), rule_id)
        assert (result.rule is not None) == expected_found


class TestLoadRuleForExplainClean:
    """suggests close matches when rule id not found."""

    def test_suggests_close_matches(self, tmp_path):
        cfg = tmp_path / "enforcer_config.py"
        cfg.write_text('''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
RULES = [
    Rule(id="no-raw-hex", severity=Severity.ERROR, matchers=[RegexMatcher(r"#fff")], file_globs=["*.ts"], message="m"),
    Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print")], file_globs=["*.py"], message="m"),
]
WORKSPACE = "."
''')
        result = load_rule_for_explain(str(cfg), "no-raw-he")
        assert result.rule is None
        assert "no-raw-hex" in result.suggestions


from enforcer.combinators import AllOf
from enforcer.matchers import ImportMatcher


class TestCombinatorRecursionFound:
    """recurses into combinators to explain inner matchers."""

    @pytest.mark.parametrize("combinator_factory", [
        lambda: AllOf([RegexMatcher(pattern=r"x"), RegexMatcher(pattern=r"y")]),
    ])
    def test_renders_inner_matchers(self, combinator_factory):
        combinator = combinator_factory()
        rule = Rule(
            id="combo-rule",
            severity=Severity.ERROR,
            matchers=[combinator],
            file_globs=["*.py"],
            message="m",
        )
        text = render_rule_explainer(rule, workspace=".")
        # the combinator itself is listed
        assert "AllOf" in text
        # inner matchers are reflected
        assert "RegexMatcher" in text


class TestCombinatorRecursionClean:
    """handles nested combinators without crash."""

    def test_nested_combinator(self):
        nested = AllOf([AllOf([RegexMatcher(pattern=r"z")])])
        rule = Rule(id="nested", severity=Severity.ERROR, matchers=[nested], file_globs=["*.py"], message="m")
        text = render_rule_explainer(rule, workspace=".")
        assert "Rule: nested" in text  # did not crash


from enforcer import matchers as matcher_pkg


class TestAllMatchersHaveStructuredDocstring:
    """every exported matcher class has What: and Basis: in its docstring."""

    @pytest.mark.parametrize("class_name", matcher_pkg.__all__)
    def test_has_what_and_basis(self, class_name):
        cls = getattr(matcher_pkg, class_name)
        doc = inspect.getdoc(cls) or ""
        sections = _parse_docstring_sections(doc)
        assert "What" in sections, f"{class_name} missing 'What:' docstring section"
        assert "Basis" in sections, f"{class_name} missing 'Basis:' docstring section"


class TestMatcherDocstringStructuredRule:
    """the matcher-docstring-structured rule is configured and would catch missing What:."""

    def test_rule_exists_in_config(self):
        from enforcer.config import load_config
        config = load_config("enforcer_config")
        rule_ids = [r.id for r in config.rules]
        assert "matcher-docstring-structured" in rule_ids


class TestMatcherTestPositiveNegativeRule:
    """the matcher-test-positive-negative rule is configured."""

    def test_rule_exists_in_config(self):
        from enforcer.config import load_config
        config = load_config("enforcer_config")
        rule_ids = [r.id for r in config.rules]
        assert "matcher-test-positive-negative" in rule_ids
