import pytest
from enforcer import FileContext, Needs, Match
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys


def _ctx(path, raw):
    return FileContext(path=path, raw=raw)


def test_keyset_sync_finds_missing_keys():
    source = _ctx(".env.config.example", "FOO=bar\nBAZ=qux\nMISSING=1\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n  BAZ = \"b\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "MISSING"
    assert matches[0].file == ".env.config.example"
    assert matches[0].line == 0


def test_keyset_sync_all_present():
    source = _ctx(".env", "FOO=1\nBAZ=2\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n  BAZ = \"b\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_exclude_keys_removed_from_used():
    source = _ctx(".env", "FOO=1\nDEV_ONLY=2\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
        exclude_keys={"DEV_ONLY"},
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_multiple_globs_union():
    source = _ctx(".env", "A=1\nB=2\nC=3\n")
    shared = {
        "dev/main.tf": _ctx("dev/main.tf", "app_environment = {\n  A = \"1\"\n}\n"),
        "prod/main.tf": _ctx("prod/main.tf", "app_environment = {\n  B = \"2\"\n  C = \"3\"\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["dev/*.tf", "prod/*.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_multiple_files_per_glob():
    source = _ctx(".env", "A=1\nB=2\n")
    shared = {
        "infra/dev/main.tf": _ctx("infra/dev/main.tf", "app_environment = {\n  A = \"1\"\n}\n"),
        "infra/prod/main.tf": _ctx("infra/prod/main.tf", "app_environment = {\n  B = \"2\"\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_empty_shared_ctx():
    source = _ctx(".env", "FOO=1\n")
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, {}) == []


def test_keyset_sync_skips_double_underscore_keys():
    source = _ctx(".env", "FOO=1\n")
    shared = {
        "__rules__": _ctx("__rules__", "app_environment = {\n  FOO = \"1\"\n}\n"),
        "__workspace__": ".",
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*"],
    )
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "FOO"


def test_keyset_sync_self_matching_guard():
    """Source file appearing in target_globs must not satisfy its own check."""
    source = _ctx("config.tf", "app_environment = {\n  FOO = \"1\"\n}\n")
    shared = {"config.tf": source}
    matcher = KeySetSyncMatcher(
        source_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*.tf"],
    )
    # Source has FOO; without the guard, it would satisfy itself → []. With the
    # guard, no target contributes → FOO is missing → 1 match.
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "FOO"


def test_keyset_sync_empty_target_globs_raises():
    with pytest.raises(ValueError, match="target_globs"):
        KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[],
        )


def test_keyset_sync_needs_raw():
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*.tf"],
    )
    assert matcher.needs == Needs.RAW


def test_keyset_sync_sorted_output():
    source = _ctx(".env", "ZEBRA=1\nALPHA=2\nMIKE=3\n")
    shared = {
        "dev/main.tf": _ctx("dev/main.tf", "app_environment = {\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["dev/*.tf"],
    )
    matches = matcher.find(source, shared)
    values = [m.matched_value for m in matches]
    assert values == ["ALPHA", "MIKE", "ZEBRA"]
