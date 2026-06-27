"""Tests that ASML example config loads with new matchers."""
from enforcer.config import load_config

def test_asml_config_loads():
    config = load_config("examples/asml_enforcer_config.py")
    rule_ids = [r.id for r in config.rules]
    assert "backend-no-import-jobs" in rule_ids
    assert "backend-function-max-lines" in rule_ids
    assert "backend-test-paired" in rule_ids
    assert "frontend-test-paired" in rule_ids

def test_paired_matcher_replaces_file_exists():
    """backend-test-paired should use PairedFileMatcher, not FileExistsMatcher+Not."""
    from enforcer.matchers.paired_file import PairedFileMatcher
    config = load_config("examples/asml_enforcer_config.py")
    test_rule = next(r for r in config.rules if r.id == "backend-test-paired")
    assert any(isinstance(m, PairedFileMatcher) for m in test_rule.matchers)

def test_import_rule_uses_import_matcher():
    from enforcer.matchers.import_matcher import ImportMatcher
    config = load_config("examples/asml_enforcer_config.py")
    import_rule = next(r for r in config.rules if r.id == "backend-no-import-jobs")
    assert any(isinstance(m, ImportMatcher) for m in import_rule.matchers)

def test_complexity_rule_uses_function_complexity_matcher():
    from enforcer.matchers.function_complexity import FunctionComplexityMatcher
    config = load_config("examples/asml_enforcer_config.py")
    complexity_rule = next(r for r in config.rules if r.id == "backend-function-max-lines")
    assert any(isinstance(m, FunctionComplexityMatcher) for m in complexity_rule.matchers)
