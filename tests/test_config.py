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
    from enforcer.types import LLMConfig
    config_content = '''
from enforcer import Rule, Severity, LLMConfig
LLM_CONFIG = LLMConfig(concurrency=3, timeout=60)
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert isinstance(config.llm_config, LLMConfig)
    assert config.llm_config.concurrency == 3
    assert config.llm_config.timeout == 60


def test_config_llm_config_dict_coerced():
    """Dict-style LLM_CONFIG is coerced into LLMConfig object."""
    from enforcer.types import LLMConfig
    config_content = '''
from enforcer import Rule, Severity
LLM_CONFIG = {"concurrency": 2, "timeout": 90, "default_provider": "openai", "default_model": "gpt-4o"}
RULES = []
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(f.name)

    assert isinstance(config.llm_config, LLMConfig)
    assert config.llm_config.concurrency == 2
    assert config.llm_config.default_provider == "openai"
    assert config.llm_config.default_model == "gpt-4o"


def test_load_config_from_package(tmp_path):
    """load_config should handle package directories, not just .py files."""
    import sys
    import importlib
    pkg_dir = tmp_path / "my_config_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "from enforcer import Rule, Severity\n"
        "RULES = []\n"
        "WORKSPACE = '.'\n"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        config = load_config("my_config_pkg")
        assert config.rules == []
        assert config.workspace == "."
    finally:
        sys.path.remove(str(tmp_path))
        if "my_config_pkg" in sys.modules:
            del sys.modules["my_config_pkg"]
