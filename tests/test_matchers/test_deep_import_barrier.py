"""Tests for DeepImportBarrierMatcher: flags cross-module imports bypassing a module's facade."""
import pytest
from enforcer.matchers.deep_import_barrier import DeepImportBarrierMatcher
from enforcer.types import FileContext, Needs


def _ctx(path: str) -> FileContext:
    return FileContext(path=path, raw="# stub")


class TestDeepImportBarrierFlags:
    """flags cross-module imports that land below a module's entry points."""

    @pytest.mark.parametrize("src,target,expected", [
        ("pkg/a/foo.py", "pkg/b/internal.py",
         "pkg/b/internal.py (deep import into pkg/b; import its entry point)"),
        ("app/main.py", "pkg/b/internal.py",              # source outside any module
         "pkg/b/internal.py (deep import into pkg/b; import its entry point)"),
        ("pkg/a/foo.py", "pkg/b/sub/deep.py",             # nested deep target
         "pkg/b/sub/deep.py (deep import into pkg/b; import its entry point)"),
    ])
    def test_flags_deep_import(self, src, target, expected):
        graph = {src: {target}}
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        matches = matcher.find(_ctx(src), {"__import_graph__": graph})
        assert len(matches) == 1
        assert matches[0].file == src
        assert matches[0].matched_value == expected

    def test_one_match_per_deep_edge(self):
        graph = {"pkg/a/foo.py": {"pkg/b/internal.py", "pkg/c/guts.py"}}
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        matches = matcher.find(_ctx("pkg/a/foo.py"), {"__import_graph__": graph})
        assert len(matches) == 2


class TestDeepImportBarrierClean:
    """does not flag entry-point targets, intra-module, or ungoverned targets."""

    @pytest.mark.parametrize("target,entry_points", [
        ("pkg/b/__init__.py", ["__init__.py"]),           # default facade
        ("pkg/b/api.py", ["__init__.py", "api.py"]),      # custom facade
        ("pkg/b/public/thing.py", ["public/*.py"]),       # glob facade
        ("pkg/a/internal.py", ["__init__.py"]),           # intra-module deep import
        ("shared/db.py", ["__init__.py"]),                # target in no governed module
        ("pkgx/b/internal.py", ["__init__.py"]),          # 'pkgx' not under 'pkg/*'
    ])
    def test_clean_allowed_target(self, target, entry_points):
        graph = {"pkg/a/foo.py": {target}}
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*", entry_points=entry_points)
        assert not matcher.find(_ctx("pkg/a/foo.py"), {"__import_graph__": graph})

    def test_clean_no_graph_returns_empty(self):
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        assert not matcher.find(_ctx("pkg/a/foo.py"), shared_ctx={})


class TestDeepImportBarrierModuleResolution:
    """_module_of resolves the module-root directory for a path."""

    @pytest.mark.parametrize("path,expected", [
        ("pkg/b/internal.py", "pkg/b"),
        ("pkg/b/sub/deep.py", "pkg/b"),
        ("pkg/b.py", None),            # file at the star level, not inside a module dir
        ("other/b/x.py", None),        # literal prefix mismatch
        ("pkg", None),                 # too shallow
    ])
    def test_module_of(self, path, expected):
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        assert matcher._module_of(path) == expected

    def test_module_of_multi_segment_prefix(self):
        matcher = DeepImportBarrierMatcher(module_glob="src/features/*")
        assert matcher._module_of("src/features/orders/svc.py") == "src/features/orders"
        assert matcher._module_of("src/shared/db.py") is None

    def test_no_wildcard_glob_governs_nothing(self):
        matcher = DeepImportBarrierMatcher(module_glob="pkg/b")
        assert matcher._module_of("pkg/b/internal.py") is None


def test_needs_ast_py():
    assert DeepImportBarrierMatcher(module_glob="pkg/*").needs == Needs.AST_PY


def test_reads_import_graph_marker():
    assert DeepImportBarrierMatcher(module_glob="pkg/*").reads_import_graph is True


class TestDeepImportBarrierLineAttribution:
    """line attribution comes from __import_lines__ recorded by the resolver."""

    def test_line_from_import_lines(self):
        ctx = FileContext(path="pkg/a/foo.py", raw="# stub")
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        graph = {"pkg/a/foo.py": {"pkg/b/internal.py"}}
        import_lines = {"pkg/a/foo.py": {"pkg/b/internal.py": 2}}
        matches = matcher.find(ctx, {"__import_graph__": graph, "__import_lines__": import_lines})
        assert len(matches) == 1
        assert matches[0].line == 2

    def test_line_defaults_to_zero_when_unrecorded(self):
        ctx = FileContext(path="pkg/a/foo.py", raw="# stub")
        matcher = DeepImportBarrierMatcher(module_glob="pkg/*")
        graph = {"pkg/a/foo.py": {"pkg/b/internal.py"}}
        matches = matcher.find(ctx, {"__import_graph__": graph})
        assert len(matches) == 1
        assert matches[0].line == 0
