"""Self-enforcement config for pre-commit-agent-enforcer (package form).

Composes rules from sub-config modules. Each sub-config owns a section;
this file imports and concatenates them into RULES.

Severity philosophy:
  ERROR — style/correctness violations. Always blocks. Must fix before commit.
  WARN  — critical-component reminders. Blocks unless --confirm-read-warnings.
          Fires when you touch files that have broad blast radius. The reminder
          tells you what to verify before acknowledging.

Setup (one-time):
  enforcer install --force
  export ENFORCER_CONFIG=enforcer_config
"""
from enforcer import LLMConfig, Severity
from enforcer_config.git_rules import GIT_RULES
from enforcer_config.test_rules import TEST_RULES
from enforcer_config.arch_rules import ARCH_RULES
from enforcer_config.style_rules import STYLE_RULES
from enforcer_config.hygiene_rules import HYGIENE_RULES
from enforcer_config.self_enforce import SELF_ENFORCE_RULES

WORKSPACE = "."

RULES = [
    *GIT_RULES,
    *TEST_RULES,
    *ARCH_RULES,
    *STYLE_RULES,
    *HYGIENE_RULES,
    *SELF_ENFORCE_RULES,
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}

LLM_CONFIG = LLMConfig(
    default_provider="custom",
    default_model="zai-org/GLM-5.1-FP8",
    concurrency=3,
    timeout=45,
)
