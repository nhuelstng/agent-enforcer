"""Candidate #7: FileContextBuilder and LLMExecutor accept their dependencies.

Each seam is exercised with an injected fake — no monkeypatching of module state,
no network — which is the point of accepting dependencies instead of creating them."""
from enforcer.context import FileContextBuilder
from enforcer.llm import LLMExecutor
from enforcer.types import Match, FileContext, LLMConsequence, Needs


def test_file_context_builder_uses_injected_parser(tmp_path):
    """The builder parses via the injected parser, not the hard-coded tree-sitter one."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    calls = []

    def fake_parser(raw, need):
        calls.append((raw, need))
        return f"AST<{need.value}>"

    rule = type("R", (), {"file_globs": ["**/*.py"], "exclude_globs": [],
                          "matchers": [type("M", (), {"needs": Needs.AST_PY})()]})()
    builder = FileContextBuilder([rule], workspace=str(tmp_path), parser=fake_parser)
    ctx = builder.build("a.py")

    assert ctx.ast == "AST<ast_py>"
    assert calls == [("x = 1\n", Needs.AST_PY)]


def test_file_context_builder_defaults_to_real_parser(tmp_path):
    """Omitting the parser keeps the real tree-sitter behaviour (raw still read)."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = FileContextBuilder([], workspace=str(tmp_path)).build("a.py")
    assert ctx.raw == "x = 1\n"


def test_llm_executor_uses_injected_caller():
    """LLMExecutor routes through the injected caller instead of the network transport."""
    seen = {}

    def fake_caller(provider, model, prompt, timeout, llm_config):
        seen["prompt"] = prompt
        return "fake-response"

    executor = LLMExecutor(enabled=True, caller=fake_caller)
    ctx = FileContext(path="x.py", raw="print()\n")
    consequence = LLMConsequence(provider="p", model="m", prompt="check this")
    result = executor.execute([Match(file="x.py", line=1)], consequence, ctx)

    assert all(m.llm_response == "fake-response" for m in result)
    assert "check this" in seen["prompt"]


def test_llm_executor_disabled_skips_caller():
    """A disabled executor never invokes the caller."""
    called = []
    executor = LLMExecutor(enabled=False, caller=lambda *a, **k: called.append(1) or "x")
    ctx = FileContext(path="x.py", raw="print()\n")
    consequence = LLMConsequence(provider="p", model="m", prompt="check")
    executor.execute([Match(file="x.py", line=1)], consequence, ctx)
    assert called == []
