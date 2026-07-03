"""Tests for shared glob_match util — supports ** recursive globs."""
import pytest
from enforcer.glob_util import glob_match


class TestGlobMatch:
    @pytest.mark.parametrize("path,pattern,expected", [
        ("enforcer/matchers/regex.py", "enforcer/**/*.py", True),
        ("enforcer/a/b/c.py", "enforcer/**/*.py", True),
        ("enforcer/a/b/c/d.py", "enforcer/**/*.py", True),
        ("enforcer/x.py", "enforcer/**/*.py", True),
        ("a/b/c/d.py", "**/d.py", True),
        ("d.py", "**/d.py", True),
        ("d.py", "*.py", True),
        ("foo/bar.py", "*.py", True),  # fnmatch * crosses / — existing behavior
        ("foo/bar.py", "foo/*.py", True),
    ])
    def test_glob_match(self, path, pattern, expected):
        assert glob_match(path, pattern) is expected
