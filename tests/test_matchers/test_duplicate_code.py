"""Tests for DuplicateCodeMatcher: token-based n-gram similarity detection."""
from enforcer.matchers.duplicate_code import DuplicateCodeMatcher
from enforcer.types import FileContext


def test_no_duplicates_returns_empty():
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)
    ctx_a = FileContext(path="a.py", raw="def foo():\n    return 1\n")
    ctx_b = FileContext(path="b.py", raw="def bar():\n    return 2\n")
    shared = {}
    matcher.find(ctx_a, shared)
    matcher.find(ctx_b, shared)
    assert matcher.finalize_duplicates(shared) == []


def test_identical_files_flagged():
    code = "def process(data):\n    result = []\n    for item in data:\n        result.append(item * 2)\n    return result\n"
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)
    ctx_a = FileContext(path="a.py", raw=code)
    ctx_b = FileContext(path="b.py", raw=code)
    shared = {}
    matcher.find(ctx_a, shared)
    matcher.find(ctx_b, shared)
    matches = matcher.finalize_duplicates(shared)
    assert len(matches) == 2
    assert matches[0].file == "a.py"
    assert "b.py" in matches[0].matched_value
    assert matches[1].file == "b.py"
    assert "a.py" in matches[1].matched_value


def test_partial_overlap_flagged():
    shared_code = "x = 1\ny = 2\nz = 3\na = 4\nb = 5\nc = 6\nd = 7\ne = 8\nf = 9\ng = 10\n"
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.5)
    ctx_a = FileContext(path="a.py", raw=shared_code + "unique_a = 11\n")
    ctx_b = FileContext(path="b.py", raw=shared_code + "unique_b = 12\n")
    shared = {}
    matcher.find(ctx_a, shared)
    matcher.find(ctx_b, shared)
    matches = matcher.finalize_duplicates(shared)
    assert len(matches) == 2


def test_low_overlap_not_flagged():
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.9)
    ctx_a = FileContext(path="a.py", raw="x = 1\ny = 2\nz = 3\na = 4\nb = 5\nunique = 99\n")
    ctx_b = FileContext(path="b.py", raw="x = 1\ny = 2\nz = 3\na = 4\nb = 5\ndifferent = 88\n")
    shared = {}
    matcher.find(ctx_a, shared)
    matcher.find(ctx_b, shared)
    matches = matcher.finalize_duplicates(shared)
    assert matches == []


def test_three_files_all_duplicate():
    code = "def foo():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)
    shared = {}
    for path in ["a.py", "b.py", "c.py"]:
        matcher.find(FileContext(path=path, raw=code), shared)
    matches = matcher.finalize_duplicates(shared)
    # 3 pairs * 2 matches each = 6
    assert len(matches) == 6


def test_empty_file_skipped():
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)
    shared = {}
    matcher.find(FileContext(path="empty.py", raw=""), shared)
    matcher.find(FileContext(path="empty2.py", raw=""), shared)
    assert matcher.finalize_duplicates(shared) == []


def test_no_raw_skipped():
    matcher = DuplicateCodeMatcher(min_tokens=5, min_overlap=0.8)
    ctx = FileContext(path="none.py", raw=None)
    assert matcher.find(ctx, {}) == []


def test_finalize_without_find_returns_empty():
    matcher = DuplicateCodeMatcher()
    assert matcher.finalize_duplicates({}) == []


def test_whitespace_and_comments_ignored():
    """Tokenizer should strip comments and treat whitespace as separators only."""
    code_a = "def foo():\n    # comment\n    return 42\n"
    code_b = "def foo():\n    return 42\n"
    matcher = DuplicateCodeMatcher(min_tokens=3, min_overlap=0.8)
    shared = {}
    matcher.find(FileContext(path="a.py", raw=code_a), shared)
    matcher.find(FileContext(path="b.py", raw=code_b), shared)
    matches = matcher.finalize_duplicates(shared)
    assert len(matches) == 2
