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
