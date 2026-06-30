import re
import pytest
from enforcer import FileContext, Needs
from enforcer.matchers import AllowlistMatcher

def test_allowlist_finds_undefined():
    target_raw = "--color-primary: #fff; --color-secondary: #000;"
    file_raw = "var(--color-primary); var(--color-undefined); var(--color-missing);"
    target_ctx = FileContext(path="colors.scss", raw=target_raw)
    file_ctx = FileContext(path="x.ts", raw=file_raw)
    shared = {"colors.scss": target_ctx}
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    matches = matcher.find(file_ctx, shared)
    assert len(matches) == 2
    values = {m.matched_value for m in matches}
    assert values == {"color-undefined", "color-missing"}

def test_allowlist_all_defined():
    import re
    target_raw = "--color-primary: #fff; --color-secondary: #000;"
    file_raw = "var(--color-primary); var(--color-secondary);"
    shared = {"colors.scss": FileContext(path="colors.scss", raw=target_raw)}
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    matches = matcher.find(FileContext(path="x.ts", raw=file_raw), shared)
    assert matches == []

def test_allowlist_missing_target():
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(),
        consumer=lambda raw: {"foo"},
        read_target="**/missing.scss",
    )
    matches = matcher.find(FileContext(path="x.ts", raw=""), {})
    assert matches == []

def test_allowlist_needs_raw():
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(),
        consumer=lambda raw: set(),
        read_target="**/colors.scss",
    )
    assert matcher.needs == Needs.RAW


def test_allowlist_multi_file_glob_union(tmp_path):
    """AllowlistMatcher should union keys across ALL files matching the read_target glob."""
    matcher = AllowlistMatcher(
        extractor=lambda raw: set(raw.split()),
        consumer=lambda raw: set(raw.split()),
        read_target="**/allowlist.txt",
    )
    ctx = FileContext(path="x.py", raw="SECRET_KEY\nSAFE_KEY\n")
    shared_ctx = {
        "__workspace__": ".",
        "dir1/allowlist.txt": FileContext(path="dir1/allowlist.txt", raw="SAFE_KEY\n"),
        "dir2/allowlist.txt": FileContext(path="dir2/allowlist.txt", raw="SECRET_KEY\n"),
    }
    matches = matcher.find(ctx, shared_ctx=shared_ctx)
    assert matches == []
