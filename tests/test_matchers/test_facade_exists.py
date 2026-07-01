"""Tests for FacadeExistsMatcher: flags directories matching source_glob missing a facade file."""
import pytest
from enforcer.matchers.facade_exists import FacadeExistsMatcher
from enforcer.types import FileContext, Needs


class TestFacadeExistsFlags:
    """flags directories missing a facade file."""

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts", "mod.py"])
    def test_fail_flags_missing_facade(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "foo.ts").write_text("x = 1\n")

        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        matches = matcher.find(ctx)
        assert len(matches) == 1
        assert facade in matches[0].matched_value

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts", "mod.py"])
    def test_fail_flags_missing_facade_empty_dir(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        matches = matcher.find(ctx)
        assert len(matches) == 1


class TestFacadeExistsClean:
    """does not flag when facade exists or dir doesn't match."""

    @pytest.mark.parametrize("facade", ["__init__.py", "index.ts", "mod.py"])
    def test_success_clean_when_facade_exists(self, tmp_path, facade):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / facade).write_text("export = 1\n")

        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade=facade,
            workspace=str(tmp_path),
        )
        ctx = FileContext(path="services/foo.ts", raw="x = 1\n")
        assert matcher.find(ctx) == []

    @pytest.mark.parametrize("path", ["other/foo.py", "other/bar.ts", "unrelated/baz.py"])
    def test_success_clean_non_matching_dir(self, tmp_path, path):
        matcher = FacadeExistsMatcher(
            source_glob="services/*",
            facade="__init__.py",
            workspace=str(tmp_path),
        )
        ctx = FileContext(path=path, raw="x = 1\n")
        assert matcher.find(ctx) == []

    def test_needs_raw(self):
        assert FacadeExistsMatcher(source_glob="*", facade="x").needs == Needs.RAW
