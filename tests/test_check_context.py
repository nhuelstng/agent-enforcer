"""Tests for CheckContext: the typed, dict-backed per-run container."""
import pytest
from enforcer.check_context import CheckContext
from enforcer.types import FileContext, ChangeContext, LLMConfig


def test_defaults():
    ctx = CheckContext()
    assert ctx.rules == []
    assert ctx.workspace == "."
    assert ctx.rendered_doc == ""
    assert ctx.change is None
    assert ctx.llm_enabled is True
    assert ctx.llm_config is None
    assert ctx.all_files is False
    assert ctx.import_graph == {}
    assert ctx.import_lines == {}


def test_constructor_typed_reads():
    cc = ChangeContext(commit_msg="feat: x")
    cfg = LLMConfig(default_model="m")
    ctx = CheckContext(rules=["r"], workspace="/w", rendered_doc="doc",
                       change=cc, llm_enabled=False, llm_config=cfg, all_files=True)
    assert ctx.rules == ["r"]
    assert ctx.workspace == "/w"
    assert ctx.rendered_doc == "doc"
    assert ctx.change is cc
    assert ctx.llm_enabled is False
    assert ctx.llm_config is cfg
    assert ctx.all_files is True


def test_setters_write_through():
    ctx = CheckContext()
    cc = ChangeContext(branch="feature/y")
    ctx.change = cc
    ctx.llm_enabled = False
    ctx.llm_config = LLMConfig()
    ctx.all_files = True
    assert ctx.change is cc
    assert ctx.llm_enabled is False
    assert isinstance(ctx.llm_config, LLMConfig)
    assert ctx.all_files is True


def test_set_import_graph():
    ctx = CheckContext()
    graph = {"a.py": {"b.py"}}
    lines = {"a.py": {"b.py": 3}}
    ctx.set_import_graph(graph, lines)
    assert ctx.import_graph == graph
    assert ctx.import_lines == lines


def test_of_passthrough_preserves_identity():
    ctx = CheckContext()
    assert CheckContext.of(ctx) is ctx


@pytest.mark.parametrize("raw", [
    {"__import_graph__": {"a.py": {"b.py"}}},
    {"__rendered_doc__": "hello"},
    {},
])
def test_of_wraps_plain_dict(raw):
    wrapped = CheckContext.of(raw)
    assert isinstance(wrapped, CheckContext)
    assert dict(wrapped) == raw


def test_of_none_is_empty():
    assert dict(CheckContext.of(None)) == {}


def test_of_reads_legacy_keys():
    wrapped = CheckContext.of({"__import_graph__": {"a": {"b"}}, "__rendered_doc__": "d"})
    assert wrapped.import_graph == {"a": {"b"}}
    assert wrapped.rendered_doc == "d"


def test_file_ctx_o1_lookup():
    ctx = CheckContext()
    fc = FileContext(path="pkg/a.py", raw="x")
    ctx.cache_file("pkg/a.py", fc)
    assert ctx.file_ctx("pkg/a.py") is fc
    assert ctx.file_ctx("missing.py") is None


def test_file_ctx_ignores_non_filecontext_values():
    ctx = CheckContext(rules=["r"])
    # a reserved slot holds a list, not a FileContext
    assert ctx.file_ctx("__rules__") is None


def test_files_excludes_reserved_and_non_filecontexts():
    ctx = CheckContext(workspace=".")
    fc = FileContext(path="cfg.txt", raw="k")
    ctx.cache_file("cfg.txt", fc)
    ctx["__cycle_reach__"] = {}  # matcher scratch — reserved prefix, must be excluded
    files = ctx.files
    assert files == {"cfg.txt": fc}


def test_is_a_dict_for_backward_compat():
    ctx = CheckContext()
    # legacy mapping operations still work (matcher scratch, iteration)
    ctx.setdefault("__cycle_reach__", {})["a"] = {"b"}
    assert ctx["__cycle_reach__"] == {"a": {"b"}}
    assert "__rules__" in ctx
