"""Tests for PairedFileMatcher: cross-file paired file existence checks."""
import tempfile
from pathlib import Path
import pytest
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

# Directory depths below the `**` prefix; the 2- and 3-level cases regressed
# when glob.glob ran without recursive=True. Inlined in each decorator (the
# coverage self-check counts inline list literals, not variable references).
@pytest.mark.parametrize("nested_dir", ["foo", "components/foo", "components/ui/foo"])
def test_paired_file_doublestar_colocated_spec_clean(nested_dir):
    """`**` in derived_glob must find a co-located pair nested any depth deep.

    Regression: glob.glob without recursive=True collapses `**` to a single `*`,
    so specs nested >1 level below the prefix were reported missing (false positive).
    """
    segments = nested_dir.split("/")
    with tempfile.TemporaryDirectory() as tmpdir:
        comp_dir = Path(tmpdir, "frontend", "src", "app", *segments)
        comp_dir.mkdir(parents=True)
        (comp_dir / "widget.component.ts").write_text("x = 1")
        (comp_dir / "widget.component.spec.ts").write_text("x = 1")

        rel = "/".join(("frontend", "src", "app", *segments, "widget.component.ts"))
        matcher = PairedFileMatcher(
            source_glob="frontend/src/app/**/*.component.ts",
            derived_glob="frontend/src/app/**/{stem}.spec.ts",
            workspace=tmpdir,
        )
        ctx = FileContext(path=rel, raw="x = 1")
        assert not matcher.find(ctx, shared_ctx={})


@pytest.mark.parametrize("nested_dir", ["foo", "components/foo", "components/ui/foo"])
def test_paired_file_doublestar_missing_spec_flags(nested_dir):
    """`**` derived_glob still flags a genuinely missing co-located spec at any depth."""
    segments = nested_dir.split("/")
    with tempfile.TemporaryDirectory() as tmpdir:
        comp_dir = Path(tmpdir, "frontend", "src", "app", *segments)
        comp_dir.mkdir(parents=True)
        (comp_dir / "widget.component.ts").write_text("x = 1")  # no spec

        rel = "/".join(("frontend", "src", "app", *segments, "widget.component.ts"))
        matcher = PairedFileMatcher(
            source_glob="frontend/src/app/**/*.component.ts",
            derived_glob="frontend/src/app/**/{stem}.spec.ts",
            workspace=tmpdir,
        )
        ctx = FileContext(path=rel, raw="x = 1")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1
        assert "widget.component.spec.ts" in matches[0].matched_value


@pytest.mark.parametrize("status", ["modified", "renamed", "deleted"])
def test_paired_file_statuses_skips_non_added_clean(status):
    """statuses={'added'} must not flag a source file with a non-added git status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "artifacts.py").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}.py",
            workspace=tmpdir,
            statuses={"added"},
        )
        ctx = FileContext(path="backend/app/api/artifacts.py", raw="x = 1", status=status)
        assert not matcher.find(ctx, shared_ctx={})


@pytest.mark.parametrize("derived", [
    "backend/tests/integration/test_{stem}.py",
    "backend/tests/test_{stem}.py",
    "tests/test_{stem}.py",
])
def test_paired_file_statuses_flags_added(derived):
    """statuses={'added'} still flags a newly-added source file missing its pair."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "backend", "app", "api").mkdir(parents=True)
        Path(tmpdir, "backend", "app", "api", "artifacts.py").write_text("x = 1")

        matcher = PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob=derived,
            workspace=tmpdir,
            statuses={"added"},
        )
        ctx = FileContext(path="backend/app/api/artifacts.py", raw="x = 1", status="added")
        matches = matcher.find(ctx, shared_ctx={})
        assert len(matches) == 1


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
