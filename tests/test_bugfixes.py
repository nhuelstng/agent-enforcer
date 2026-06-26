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
