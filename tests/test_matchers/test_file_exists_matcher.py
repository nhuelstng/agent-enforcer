import pytest
from enforcer.matchers import FileExistsMatcher
from enforcer.types import FileContext


def test_file_exists_when_target_exists(tmp_path):
    (tmp_path / "colors.scss").write_text("--color-red: #f00;\n")
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    matcher = FileExistsMatcher(read_target="colors.scss", workspace=str(tmp_path))
    matches = matcher.find(ctx, {})
    assert len(matches) == 1
    assert "exists" in matches[0].matched_value


def test_file_exists_when_target_missing():
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    matcher = FileExistsMatcher(read_target="missing.scss", workspace=".")
    matches = matcher.find(ctx, {})
    assert len(matches) == 0


def test_file_exists_via_shared_ctx():
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    shared = {"colors.scss": FileContext(path="colors.scss", raw="--x: 1;")}
    matcher = FileExistsMatcher(read_target="colors.scss")
    matches = matcher.find(ctx, shared)
    assert len(matches) == 1
