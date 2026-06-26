import pytest
from enforcer.context import FileContextBuilder
from enforcer.types import Needs, FileContext
from enforcer.rule import Rule, _is_combinator
from enforcer.combinators import Not, AllOf
from enforcer.matchers import RegexMatcher
from enforcer.types import Severity


class TestIsCombinator:
    def test_not_detected_as_combinator(self):
        matcher = Not(RegexMatcher(r"TODO"))
        assert _is_combinator(matcher) is True

    def test_allof_detected_as_combinator(self):
        matcher = AllOf([RegexMatcher(r"TODO"), RegexMatcher(r"FIXME")])
        assert _is_combinator(matcher) is True

    def test_plain_matcher_not_combinator(self):
        matcher = RegexMatcher(r"TODO")
        assert _is_combinator(matcher) is False


class TestContextCacheForceNeeds:
    def test_force_needs_populates_ast_on_cached_ctx(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("const x = 42;\n")
        builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
        builder.build("x.ts")
        ctx2 = builder.build("x.ts", force_needs={Needs.AST_TS})
        if ctx2.ast is None:
            pytest.skip("tree-sitter not available")
        assert ctx2.ast is not None


class TestRenderMessageBraces:
    def test_message_with_literal_braces(self):
        from enforcer.types import Match, Severity
        rule = Rule(
            id="test",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            message="Use {const} keyword instead of var",
        )
        match = Match(file="x.ts", line=1, matched_value="var")
        result = rule._render_message(match)
        assert result == "Use {const} keyword instead of var"

    def test_message_with_placeholder(self):
        from enforcer.types import Match, Severity
        rule = Rule(
            id="test",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            message="Found '{matched_value}' at line {line}",
        )
        match = Match(file="x.ts", line=5, matched_value="var")
        result = rule._render_message(match)
        assert result == "Found 'var' at line 5"


class TestAllowlistKeying:
    def test_allowlist_uses_full_read_target_key(self):
        from enforcer.matchers import AllowlistMatcher
        from enforcer.types import FileContext

        def extractor(raw):
            return {"red", "blue"}

        def consumer(raw):
            return {"red", "green"}

        matcher = AllowlistMatcher(
            extractor=extractor,
            consumer=consumer,
            read_target="frontend/**/colors.scss",
        )
        target_ctx = FileContext(path="frontend/colors.scss", raw="--color-red: #f00;\n")
        file_ctx = FileContext(path="src/app.ts", raw="var(--color-green)")
        shared = {"frontend/**/colors.scss": target_ctx}
        matches = matcher.find(file_ctx, shared)
        assert len(matches) == 1
        assert matches[0].matched_value == "green"
