"""Tests for ArchitectureMatcher: flags imports crossing forbidden layer boundaries."""
import pytest
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.types import FileContext, Needs


def _ctx(path: str) -> FileContext:
    return FileContext(path=path, raw="# stub")


_LAYERS = {
    "types": ["enforcer/types.py"],
    "core": ["enforcer/runner.py"],
    "matchers": ["enforcer/matchers/**/*.py"],
    "io": ["enforcer/cli.py"],
}
_ALLOWED = [("matchers", "types"), ("core", "types")]


class TestArchitectureMatcherFlags:
    """flags imports where (source_layer, target_layer) is forbidden."""

    @pytest.mark.parametrize("src_path", [
        "enforcer/matchers/foo.py",
        "enforcer/runner.py",
        "enforcer/types.py",
    ])
    def test_flags_forbidden_edge(self, src_path):
        graph = {
            "enforcer/matchers/foo.py": {"enforcer/cli.py"},
            "enforcer/runner.py": {"enforcer/cli.py"},
            "enforcer/types.py": {"enforcer/runner.py"},
        }
        expected = {
            "enforcer/matchers/foo.py": "matchers -> io",
            "enforcer/runner.py": "core -> io",
            "enforcer/types.py": "types -> core",
        }
        matcher = ArchitectureMatcher(
            layers=_LAYERS,
            allowed_edges=_ALLOWED,
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": graph}
        matches = matcher.find(_ctx(src_path), shared_ctx)

        assert len(matches) == 1
        assert matches[0].matched_value == expected[src_path]
        assert matches[0].file == src_path


class TestArchitectureMatcherClean:
    """does not flag allowed edges, intra-layer, or unlayered files."""

    @pytest.mark.parametrize("src_path", [
        "enforcer/matchers/foo.py",
        "enforcer/runner.py",
        "enforcer/types.py",
    ])
    def test_clean_on_allowed(self, src_path):
        graph = {
            "enforcer/matchers/foo.py": {"enforcer/types.py"},       # allowed
            "enforcer/runner.py": {"enforcer/types.py"},              # allowed
            "enforcer/types.py": {"enforcer/types.py"},               # intra-layer (self)
        }
        matcher = ArchitectureMatcher(
            layers=_LAYERS,
            allowed_edges=_ALLOWED,
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": graph}
        matches = matcher.find(_ctx(src_path), shared_ctx)
        assert not matches

    @pytest.mark.parametrize("src_path", [
        "scripts/foo.py",
        "enforcer/types.py",
        "scripts/bar.py",
    ])
    def test_clean_unlayered(self, src_path):
        graph = {
            "scripts/foo.py": {"enforcer/types.py"},
            "enforcer/types.py": {"scripts/foo.py"},
            "scripts/bar.py": {"scripts/qux.py"},
        }
        matcher = ArchitectureMatcher(
            layers={"types": ["enforcer/types.py"]},
            allowed_edges=[],
            forbid_implicit=True,
        )
        shared_ctx = {"__import_graph__": graph}
        assert not matcher.find(_ctx(src_path), shared_ctx)

    def test_clean_no_graph_returns_empty(self):
        matcher = ArchitectureMatcher(layers={"a": ["a.py"]}, forbid_implicit=True)
        assert not matcher.find(_ctx("a.py"), shared_ctx={})

    def test_forbid_implicit_false_uses_forbidden_edges(self):
        layers = {"a": ["a.py"], "b": ["b.py"]}
        matcher = ArchitectureMatcher(
            layers=layers,
            forbidden_edges=[("a", "b")],
            forbid_implicit=False,
        )
        shared_ctx = {"__import_graph__": {"a.py": {"b.py"}}}
        matches = matcher.find(_ctx("a.py"), shared_ctx)
        assert len(matches) == 1
        assert matches[0].matched_value == "a -> b"

    def test_needs_ast_py(self):
        assert ArchitectureMatcher(layers={}).needs == Needs.AST_PY
