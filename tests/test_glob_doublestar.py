"""Tests for ** recursive glob matching — bug: fnmatch * does not cross /."""
import pytest
from enforcer.rule import _glob_match
from enforcer.ignore import is_ignored


class TestGlobDoubleStarRule:
    def test_double_star_matches_one_level(self):
        assert _glob_match("enforcer/matchers/regex.py", "enforcer/**/*.py") is True

    def test_double_star_matches_three_levels_deep(self):
        assert _glob_match("enforcer/a/b/c.py", "enforcer/**/*.py") is True

    def test_double_star_matches_four_levels_deep(self):
        assert _glob_match("enforcer/a/b/c/d.py", "enforcer/**/*.py") is True

    def test_double_star_zero_segments(self):
        assert _glob_match("enforcer/x.py", "enforcer/**/*.py") is True

    def test_double_star_leading_matches_nested(self):
        assert _glob_match("a/b/c/d.py", "**/d.py") is True

    def test_double_star_leading_matches_top(self):
        assert _glob_match("d.py", "**/d.py") is True


class TestGlobDoubleStarIgnore:
    def test_is_ignored_double_star_nested(self):
        assert is_ignored("a/b/c/d.py", ["**/d.py"]) is True

    def test_is_ignored_double_star_top(self):
        assert is_ignored("d.py", ["**/d.py"]) is True

    def test_is_ignored_dir_double_star_nested(self):
        assert is_ignored("src/a/b/c/file.ts", ["src/**/*.ts"]) is True

    def test_is_ignored_existing_behavior_preserved(self):
        assert is_ignored("foo.pyc", ["*.pyc"]) is True
        assert is_ignored("foo.py", ["*.pyc"]) is False
        assert is_ignored("src/node_modules/foo.js", ["node_modules"]) is True
        assert is_ignored("src/app/foo.js", ["node_modules"]) is False
