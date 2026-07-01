"""Tests for check_runner helpers: _has_architecture_matcher and build_shared_ctx staged_files gating."""
from unittest.mock import patch
from enforcer.check_runner import _has_architecture_matcher, build_shared_ctx


class _FakeRule:
    def __init__(self, matchers):
        self.matchers = matchers


class _ArchMatcher:
    layers = [("a", "b")]


class _PlainMatcher:
    pass


class _Combinator:
    def __init__(self, matchers):
        self.matchers = matchers


class _Wrapper:
    def __init__(self, matcher):
        self.matcher = matcher


def test_has_architecture_matcher_direct():
    assert _has_architecture_matcher([_FakeRule([_ArchMatcher()])]) is True


def test_has_architecture_matcher_nested_in_combinator():
    assert _has_architecture_matcher([_FakeRule([_Combinator([_ArchMatcher()])])]) is True


def test_has_architecture_matcher_in_wrapper():
    assert _has_architecture_matcher([_FakeRule([_Wrapper(_ArchMatcher())])]) is True


def test_has_architecture_matcher_absent():
    assert _has_architecture_matcher([_FakeRule([_PlainMatcher()])]) is False


def test_has_architecture_matcher_empty():
    assert _has_architecture_matcher([]) is False


def test_build_shared_ctx_skips_graph_without_arch_matcher():
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity

    config = Config(
        rules=[Rule(id="x", severity=Severity.ERROR, matchers=[_PlainMatcher()], file_globs=["*.py"])],
        workspace=".",
    )
    builder = FileContextBuilder(config.rules, workspace=".")
    with patch("enforcer.import_graph.ImportGraphBuilder") as mock_gb:
        ctx = build_shared_ctx(config, builder, ".", staged_files=["a.py"])
        mock_gb.assert_not_called()
        assert "__import_graph__" not in ctx


def test_build_shared_ctx_skips_graph_without_staged_files():
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity

    config = Config(
        rules=[Rule(id="x", severity=Severity.ERROR, matchers=[_ArchMatcher()], file_globs=["*.py"])],
        workspace=".",
    )
    builder = FileContextBuilder(config.rules, workspace=".")
    with patch("enforcer.import_graph.ImportGraphBuilder") as mock_gb:
        ctx = build_shared_ctx(config, builder, ".", staged_files=None)
        mock_gb.assert_not_called()
        assert "__import_graph__" not in ctx


def test_build_shared_ctx_builds_graph_when_both_present():
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity

    config = Config(
        rules=[Rule(id="x", severity=Severity.ERROR, matchers=[_ArchMatcher()], file_globs=["*.py"])],
        workspace=".",
    )
    builder = FileContextBuilder(config.rules, workspace=".")
    with patch("enforcer.import_graph.ImportGraphBuilder") as mock_gb:
        mock_gb.return_value.build.return_value = {"nodes": []}
        ctx = build_shared_ctx(config, builder, ".", staged_files=["a.py", "b.py"])
        mock_gb.assert_called_once()
        assert ctx["__import_graph__"] == {"nodes": []}
