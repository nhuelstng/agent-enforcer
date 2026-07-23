"""Tests for matcher_tree: the single traversal shared by the four former walkers."""
from enforcer.matcher_tree import iter_matchers, walk_with_depth, is_combinator, _children
from enforcer.combinators import AllOf, Not
from enforcer.combinators.core import StatusGate
from enforcer.matchers import RegexMatcher


class _Leaf:
    """Minimal matcher with no child slot."""
    needs = None
    def find(self, file_ctx, shared_ctx=None):
        return []


class TestChildren:
    def test_matchers_list_slot(self):
        a, b = _Leaf(), _Leaf()
        assert _children(AllOf([a, b])) == [a, b]

    def test_single_matcher_slot(self):
        leaf = _Leaf()
        assert _children(Not(leaf)) == [leaf]

    def test_leaf_has_no_children(self):
        assert _children(_Leaf()) == []


class TestIsCombinator:
    def test_list_slot_is_combinator(self):
        assert is_combinator(AllOf([_Leaf()])) is True

    def test_single_slot_is_combinator(self):
        assert is_combinator(Not(_Leaf())) is True

    def test_leaf_is_not_combinator(self):
        assert is_combinator(_Leaf()) is False

    def test_empty_list_slot_still_combinator(self):
        assert is_combinator(AllOf([])) is True


class TestIterMatchers:
    def test_yields_every_node_including_combinators(self):
        inner = RegexMatcher(r"a")
        gate = StatusGate(inner)
        tree = AllOf([gate, RegexMatcher(r"b")])
        seen = list(iter_matchers([tree]))
        assert tree in seen and gate in seen and inner in seen
        assert len(seen) == 4

    def test_nested_single_slot_descended(self):
        leaf = RegexMatcher(r"x")
        seen = list(iter_matchers([Not(Not(leaf))]))
        assert leaf in seen


class TestWalkWithDepth:
    def test_depth_increments_with_nesting(self):
        leaf = RegexMatcher(r"x")
        flat = walk_with_depth([AllOf([leaf])])
        depths = {id(m): d for d, m in flat}
        assert depths[id(leaf)] == 1

    def test_sibling_order_preserved(self):
        a, b = RegexMatcher(r"a"), RegexMatcher(r"b")
        flat = walk_with_depth([a, b])
        top_level = [m for d, m in flat if d == 0]
        assert top_level == [a, b]
