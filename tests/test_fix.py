"""Tests for auto-fix infrastructure."""
import tempfile
from pathlib import Path
from enforcer.fix import apply_fixes, FixResult
from enforcer.types import Match, Severity, FileContext

def test_apply_fixes_simple_replacement():
    """apply_fixes should replace matched text in the file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('hello')\nprint('world')\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-print",
                  severity=Severity.ERROR, matched_value="print('hello')"),
            Match(file="test.py", line=2, column=0, rule_id="no-print",
                  severity=Severity.ERROR, matched_value="print('world')"),
        ]
        # Fix: replace print( with logger.debug(
        def fix_fn(file_ctx: FileContext, match: Match) -> str:
            raw = file_ctx.raw or ""
            lines = raw.splitlines()
            if match.line <= len(lines):
                fixed = lines[match.line - 1].replace("print(", "logger.debug(")
                lines[match.line - 1] = fixed
            return "\n".join(lines) + "\n"

        results = apply_fixes(matches, tmpdir, {"no-print": fix_fn})
        assert len(results) == 1  # one result per file
        assert "logger.debug" in fpath.read_text()
        assert "print(" not in fpath.read_text()

def test_apply_fixes_no_fix_provider():
    """apply_fixes should skip matches with no fix provider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('hello')\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-fix-rule",
                  severity=Severity.ERROR, matched_value="print('hello')"),
        ]
        results = apply_fixes(matches, tmpdir, {})
        assert len(results) == 0
        # File unchanged
        assert "print('hello')" in fpath.read_text()

def test_apply_fixes_multiple_rules():
    """apply_fixes should apply fixes from different rules to the same file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("import os\nTODO: fix this\n")

        matches = [
            Match(file="test.py", line=1, column=0, rule_id="no-os-import",
                  severity=Severity.ERROR, matched_value="import os"),
            Match(file="test.py", line=2, column=0, rule_id="no-todo",
                  severity=Severity.WARN, matched_value="TODO: fix this"),
        ]
        def fix_import(ctx, m):
            return (ctx.raw or "").replace("import os\n", "")

        def fix_todo(ctx, m):
            return (ctx.raw or "").replace("TODO: ", "FIXME: ")

        results = apply_fixes(matches, tmpdir, {
            "no-os-import": fix_import,
            "no-todo": fix_todo,
        })
        content = fpath.read_text()
        assert "import os" not in content
        assert "FIXME: fix this" in content

def test_apply_fixes_file_not_found():
    """apply_fixes should skip files that don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        matches = [
            Match(file="nonexistent.py", line=1, rule_id="x", matched_value="x"),
        ]
        results = apply_fixes(matches, tmpdir, {"x": lambda ctx, m: ""})
        assert len(results) == 0

def test_fix_result_has_summary():
    """FixResult should contain file path, matches fixed, and new content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir, "test.py")
        fpath.write_text("print('x')\n")

        matches = [
            Match(file="test.py", line=1, rule_id="no-print", matched_value="print('x')"),
        ]
        def fix_fn(ctx, m):
            return (ctx.raw or "").replace("print(", "logger.debug(")

        results = apply_fixes(matches, tmpdir, {"no-print": fix_fn})
        assert len(results) == 1
        r = results[0]
        assert r.path == "test.py"
        assert r.fixes_applied == 1
        assert "logger.debug" in r.new_content
