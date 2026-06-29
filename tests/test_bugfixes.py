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


class TestAllSkipsJunkDirs:
    def test_all_skips_junk_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("const x = 1;\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("module.exports = 1;\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "x.pyc").write_text("garbage")

        import importlib
        import enforcer.cli as cli_mod
        from click.testing import CliRunner

        config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
WORKSPACE = "."
RULES = []
'''
        (tmp_path / "enforcer_config.py").write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, [
            "check", "--all", "--workspace", str(tmp_path),
            "--config", str(tmp_path / "enforcer_config.py"),
        ])
        assert "node_modules" not in result.output
        assert "__pycache__" not in result.output


class TestLLMDedup:
    def test_llm_called_once_per_file_not_per_match(self):
        from enforcer.llm import LLMExecutor
        from enforcer.types import Match, FileContext, LLMConsequence
        from unittest.mock import patch, MagicMock

        matches = [
            Match(file="x.ts", line=1, matched_value="#fff"),
            Match(file="x.ts", line=2, matched_value="#000"),
        ]
        ctx = FileContext(path="x.ts", raw="const a = '#fff';\nconst b = '#000';\n")
        consequence = LLMConsequence(provider="test", model="test", prompt="check")

        executor = LLMExecutor(enabled=True)
        with patch("enforcer.llm.call_llm", return_value="response") as mock_call:
            result = executor.execute(matches, consequence, ctx)
        assert mock_call.call_count == 1
        assert all(m.llm_response == "response" for m in result)


class TestLLMReadTargetInjection:
    def test_llm_prompt_includes_read_target_content(self):
        from enforcer.llm import LLMExecutor
        from enforcer.types import Match, FileContext, LLMConsequence

        ctx = FileContext(path="app.ts", raw="const x = 1;")
        target_ctx = FileContext(path="colors.scss", raw="--color-red: #f00;")
        shared = {"**/colors.scss": target_ctx}
        consequence = LLMConsequence(provider="test", model="test", prompt="check")

        executor = LLMExecutor(enabled=True)
        prompt = executor._build_prompt(consequence, ctx, shared)
        assert "colors.scss" in prompt
        assert "--color-red: #f00;" in prompt
