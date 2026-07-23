from enforcer import FileContext, Needs
from enforcer.matchers import PathNotMatchingMatcher

def test_path_not_matching():
    ctx = FileContext(path="src/app/x.ts")
    matches = PathNotMatchingMatcher("**/constants.ts").find(ctx)
    assert len(matches) == 1
    assert matches[0].matched_value == "src/app/x.ts"

def test_path_matches():
    ctx = FileContext(path="src/app/constants.ts")
    matches = PathNotMatchingMatcher("**/constants.ts").find(ctx)
    assert matches == []

def test_path_needs():
    assert PathNotMatchingMatcher("*.ts").needs != Needs.RAW


import pytest


@pytest.mark.parametrize("path", ["src/app/x.ts", "lib/util.ts", "a/b/c.ts"])
def test_path_flags_violation(path):
    """Flags files whose path does not match the required glob."""
    assert PathNotMatchingMatcher("**/constants.ts").find(FileContext(path=path))


@pytest.mark.parametrize("path", ["src/app/constants.ts", "lib/constants.ts", "a/b/constants.ts"])
def test_path_passes_clean(path):
    """No match when the path satisfies the required glob."""
    assert not PathNotMatchingMatcher("**/constants.ts").find(FileContext(path=path))
