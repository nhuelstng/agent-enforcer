import pytest
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import StatusGate


@pytest.mark.parametrize("status", ["added", "modified", "deleted"])
def test_status_gate_matches_when_status_allowed(status):
    """StatusGate runs its inner matcher and reports matches for every allowed status."""
    ctx = FileContext(path="x.py", raw="print('hi')\n", status=status)
    gate = StatusGate(RegexMatcher(r"print\("), allowed_statuses={"added", "modified", "deleted"})
    assert len(gate.find(ctx)) == 1


@pytest.mark.parametrize("status", ["modified", "deleted", "renamed"])
def test_status_gate_no_match_when_status_disallowed(status):
    """StatusGate suppresses its inner matcher for any status outside allowed_statuses."""
    ctx = FileContext(path="x.py", raw="print('hi')\n", status=status)
    gate = StatusGate(RegexMatcher(r"print\("), allowed_statuses={"added"})
    assert not gate.find(ctx)


def test_status_gate_runs_when_status_allowed():
    ctx = FileContext(path="x.py", raw="print('hello')\n", status="added")
    inner = RegexMatcher(r"print\(")
    gate = StatusGate(inner, allowed_statuses={"added"})
    matches = gate.find(ctx)
    assert len(matches) == 1


def test_status_gate_skips_when_status_not_allowed():
    ctx = FileContext(path="x.py", raw="print('hello')\n", status="modified")
    inner = RegexMatcher(r"print\(")
    gate = StatusGate(inner, allowed_statuses={"added"})
    assert gate.find(ctx) == []


def test_status_gate_default_allowed_is_added():
    ctx_added = FileContext(path="x.py", raw="print()\n", status="added")
    ctx_modified = FileContext(path="x.py", raw="print()\n", status="modified")
    gate = StatusGate(RegexMatcher(r"print\("))
    assert len(gate.find(ctx_added)) == 1
    assert gate.find(ctx_modified) == []


def test_status_gate_custom_statuses():
    ctx = FileContext(path="x.py", raw="print()\n", status="deleted")
    gate = StatusGate(RegexMatcher(r"print\("), allowed_statuses={"added", "deleted"})
    assert len(gate.find(ctx)) == 1


def test_status_gate_passes_shared_ctx_to_inner():
    from enforcer.matchers import AllowlistMatcher
    import re
    target_raw = "--color-primary: #fff;"
    file_raw = "var(--color-primary);"
    shared = {"colors.scss": FileContext(path="colors.scss", raw=target_raw)}
    ctx = FileContext(path="x.ts", raw=file_raw, status="added")
    inner = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    gate = StatusGate(inner)
    matches = gate.find(ctx, shared)
    assert matches == []


def test_status_gate_needs_raw():
    """StatusGate inherits needs from inner matcher (default RAW)."""
    from enforcer.types import Needs
    from enforcer.matchers import RegexMatcher
    assert StatusGate(RegexMatcher("x")).needs == Needs.RAW


def test_status_gate_finalizer_collected():
    """A matcher with finalize_duplicates inside StatusGate must still be collected by collect_finalizers."""
    from enforcer.combinators.core import collect_finalizers
    from enforcer.matchers import RegexMatcher

    class FakeFinalizerMatcher:
        needs = None
        def find(self, file_ctx, shared_ctx=None):
            return []
        def finalize_duplicates(self, shared_ctx):
            return []

    gate = StatusGate(FakeFinalizerMatcher())
    finalizers = collect_finalizers([gate])
    assert any(hasattr(f, "finalize_duplicates") for f in finalizers)
