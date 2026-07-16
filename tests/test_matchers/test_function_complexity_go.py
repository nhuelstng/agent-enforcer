"""Go-language tests for FunctionComplexityMatcher."""
import pytest
from enforcer.matchers.function_complexity import FunctionComplexityMatcher
from enforcer.types import FileContext, Needs


def _go_ctx(source: str) -> FileContext:
    from enforcer.parsers.tree_sitter import parse
    tree = parse(source, Needs.AST_GO)
    if tree is None:
        pytest.skip("tree-sitter go grammar not available")
    return FileContext(path="main.go", raw=source, ast=tree)


@pytest.mark.parametrize("src", [
    "package main\nfunc f(a, b, c int) {}\n",
    "package main\nfunc g(a, b, c, d string) {}\n",
    "package main\nfunc (s *T) M(a, b, c int) {}\n",
])
def test_go_params_flags(src):
    """Should flag Go functions whose parameter count exceeds the budget."""
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_GO)
    assert matcher.find(_go_ctx(src))


@pytest.mark.parametrize("src", [
    "package main\nfunc f(a int) {}\n",
    "package main\nfunc g() {}\n",
    "package main\nfunc (s *T) M(a int) {}\n",
])
def test_go_params_clean(src):
    """Should not flag Go functions within the parameter budget."""
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_GO)
    assert not matcher.find(_go_ctx(src))


def test_go_params_excludes_receiver_and_results():
    """Go param count uses only the params list, not the receiver or the results tuple."""
    src = "package main\nfunc (s *T) M(a, b int, c string) (int, error) { return 0, nil }\n"
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_GO)
    matches = matcher.find(_go_ctx(src))
    assert len(matches) == 1
    assert int(matches[0].matched_value) == 3


def test_go_grouped_params_counted_individually():
    """`a, b int` declares two params even though it is a single declaration node."""
    src = "package main\nfunc f(a, b, c int) {}\n"
    matcher = FunctionComplexityMatcher(metric="params", max_value=2, needs=Needs.AST_GO)
    matches = matcher.find(_go_ctx(src))
    assert int(matches[0].matched_value) == 3


_GO_SERVER = (
    "package main\n"
    "func NewServer(a, b int) (*int, error) {\n"
    "    if a > 0 && b > 0 {\n"
    "        for i := 0; i < 3; i++ {\n"
    "            switch i {\n"
    "            case 0:\n"
    "                println(\"z\")\n"
    "            case 1:\n"
    "                println(\"o\")\n"
    "            default:\n"
    "                println(\"d\")\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    return nil, nil\n"
    "}\n"
)


def test_go_cyclomatic_counts_if_for_cases_and_logical():
    """Cyclomatic = 1 + if + && + for + 2 non-default cases = 6."""
    matcher = FunctionComplexityMatcher(metric="cyclomatic", max_value=3, needs=Needs.AST_GO)
    matches = matcher.find(_go_ctx(_GO_SERVER))
    assert len(matches) == 1
    assert int(matches[0].matched_value) == 6


def test_go_nesting_counts_switch_level():
    """Nesting func>if>for>switch = depth 4."""
    matcher = FunctionComplexityMatcher(metric="nesting", max_value=2, needs=Needs.AST_GO)
    matches = matcher.find(_go_ctx(_GO_SERVER))
    assert int(matches[0].matched_value) == 4
