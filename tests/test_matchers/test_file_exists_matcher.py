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


@pytest.mark.parametrize("target", ["colors.scss", "vars.css", "theme.less"])
def test_file_exists_flags_violation(target):
    """Emits a match when the target is present in shared_ctx."""
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    shared = {target: FileContext(path=target, raw="--x: 1;")}
    assert FileExistsMatcher(read_target=target).find(ctx, shared)


@pytest.mark.parametrize("target", ["nope.scss", "absent.css", "missing.less"])
def test_file_exists_passes_clean(target):
    """Emits no match when the target does not exist."""
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    assert not FileExistsMatcher(read_target=target, workspace=".").find(ctx, {})
