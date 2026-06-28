"""Tests for PairedFileMatcher: cross-file paired file existence checks."""
import tempfile
from pathlib import Path
from enforcer.matchers.paired_file import PairedFileMatcher
from enforcer.types import FileContext

def test_paired_file_exists():
    """Should not flag when paired file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "artifacts.py").write_text("x = 1")
        Path(tmpdir, "backend", "tests", "integration").mkdir(parents=True)
        Path(tmpdir, "backend", "tests", "integration", "test_artifacts.py").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="backend/app/api/artifacts.py", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert matches == []

def test_paired_file_missing():
    """Should flag when paired file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "artifacts.py").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="backend/app/api/artifacts.py", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1
        assert "test_artifacts.py" in matches[0].matched_value

def test_paired_file_excludes_init():
    """Should not check __init__.py files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "__init__.py").write_text("")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}.py",
            workspace=tmpdir,
            exclude_stems=["__init__", "router"],
        )
        ctx = FileContext(path="backend/app/api/__init__.py", raw="")
        matches = matcher.find(ctx, shared_ctx={})
        assert matches == []

def test_paired_file_typescript_spec():
    """Should work for TypeScript .spec.ts pairing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "frontend", "src", "app", "components", "foo").mkdir(parents=True)
        Path(tmpdir, "frontend", "src", "app", "components", "foo", "foo.component.ts").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="frontend/src/app/components/**/*.ts",
            derived_glob="frontend/src/app/components/{dir}/{stem}.spec.ts",
            workspace=tmpdir,
        )
        ctx = FileContext(path="frontend/src/app/components/foo/foo.component.ts", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1

def test_paired_file_typescript_spec_exists():
    """Should not flag when .spec.ts exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "frontend", "src", "app", "components", "foo").mkdir(parents=True)
        Path(tmpdir, "frontend", "src", "app", "components", "foo", "foo.component.ts").write_text("x = 1")
        Path(tmpdir, "frontend", "src", "app", "components", "foo", "foo.component.spec.ts").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="frontend/src/app/components/**/*.ts",
            derived_glob="frontend/src/app/components/{dir}/{stem}.spec.ts",
            workspace=tmpdir,
        )
        ctx = FileContext(path="frontend/src/app/components/foo/foo.component.ts", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert matches == []

def test_paired_file_stem_extraction():
    """Should correctly extract stem from filename (strip extension)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "admin.py").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}.py",
            workspace=tmpdir,
        )
        ctx = FileContext(path="backend/app/api/admin.py", raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1
        assert "test_admin.py" in matches[0].matched_value
