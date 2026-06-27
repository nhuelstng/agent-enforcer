"""Tests for .enforcerignore loading and matching."""
import os
import tempfile
from pathlib import Path
from enforcer.ignore import load_enforcerignore, is_ignored


def test_no_enforcerignore_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert load_enforcerignore(tmpdir) == []


def test_loads_patterns():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, ".enforcerignore").write_text(
            "*.pyc\nnode_modules/\n# comment\n\ndist/\n"
        )
        patterns = load_enforcerignore(tmpdir)
        assert "*.pyc" in patterns
        assert "node_modules/" in patterns
        assert "dist/" in patterns
        assert "# comment" not in patterns
        assert len(patterns) == 3


def test_is_ignored_simple_glob():
    assert is_ignored("foo.pyc", ["*.pyc"]) is True
    assert is_ignored("foo.py", ["*.pyc"]) is False


def test_is_ignored_basename():
    assert is_ignored("src/node_modules/foo.js", ["node_modules"]) is True
    assert is_ignored("src/app/foo.js", ["node_modules"]) is False


def test_is_ignored_directory():
    assert is_ignored("src/dist/bundle.js", ["dist/"]) is True
    assert is_ignored("src/app/bundle.js", ["dist/"]) is False


def test_is_ignored_empty_patterns():
    assert is_ignored("anything.py", []) is False


def test_is_ignored_multiple_patterns():
    patterns = ["*.pyc", "node_modules", "dist/"]
    assert is_ignored("app.pyc", patterns) is True
    assert is_ignored("node_modules/foo.js", patterns) is True
    assert is_ignored("dist/bundle.js", patterns) is True
    assert is_ignored("src/app/foo.py", patterns) is False


def test_enforcerignoric_skips_comments_and_blanks():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, ".enforcerignore").write_text(
            "# Header comment\n"
            "\n"
            "  # indented comment\n"
            "*.log\n"
            "  *.tmp  \n"
        )
        patterns = load_enforcerignore(tmpdir)
        assert patterns == ["*.log", "*.tmp"]


def test_enforcerignore_with_subdirectory_path():
    """Should match patterns against full path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, ".enforcerignore").write_text("vendor/*.php\n")
        patterns = load_enforcerignore(tmpdir)
        assert is_ignored("vendor/foo.php", patterns) is True
        assert is_ignored("app/foo.php", patterns) is False
