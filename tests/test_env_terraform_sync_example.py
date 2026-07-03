"""Tests for examples/env_terraform_sync.py — loads the example config and asserts structure."""
import pytest
from enforcer.config import load_config
from enforcer import Severity
from enforcer.matchers import KeySetSyncMatcher


@pytest.fixture
def example_config():
    return load_config("examples/env_terraform_sync.py")


def test_example_config_loads(example_config):
    assert len(example_config.rules) >= 1
    assert example_config.workspace == "."


def test_example_config_has_env_tf_sync_rule(example_config):
    rule = next(r for r in example_config.rules if r.id == "env-tf-config-sync")
    assert rule.severity == Severity.ERROR
    assert ".env.example" in rule.file_globs
    assert "infrastructure/*/main.tf" in rule.read_targets
    assert any(isinstance(m, KeySetSyncMatcher) for m in rule.matchers)


def test_example_config_severity_actions(example_config):
    assert example_config.severity_actions[Severity.ERROR] == "block"
    assert example_config.severity_actions[Severity.WARN] == "block_warn"
    assert example_config.severity_actions[Severity.INFO] == "hint"


def test_example_config_dev_local_keys_exclude(example_config):
    rule = next(r for r in example_config.rules if r.id == "env-tf-config-sync")
    matcher = next(m for m in rule.matchers if isinstance(m, KeySetSyncMatcher))
    assert "LOG_LEVEL" in matcher.exclude_keys
    assert "DEBUG" in matcher.exclude_keys
