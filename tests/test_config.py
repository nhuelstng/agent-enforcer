import pytest
import tempfile
import os
from enforcer import Severity
from enforcer.config import Config, load_config

def test_config_loads_rules():
    config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

WORKSPACE = "."
RULES = [
    Rule(
        id="test-rule",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#fff")],
        file_globs=["**/*.ts"],
        message="Found hex",
    ),
]
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.workspace == "."
    assert len(config.rules) == 1
    assert config.rules[0].id == "test-rule"

def test_config_severity_actions():
    config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "print",
}
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.severity_actions[Severity.ERROR] == "block"

def test_config_default_workspace():
    config_content = '''
from enforcer import Rule, Severity
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.workspace == "."

def test_config_llm_config():
    config_content = '''
from enforcer import Rule, Severity
LLM_CONFIG = {"concurrency": 3, "timeout": 60}
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert config.llm_config["concurrency"] == 3
