"""Convention enforcement DSL for coding agents. Public API: Rule, Severity, Needs, RuleType, Match, FileContext, LLMConsequence, LLMConfig, ProviderConfig, ChangeContext."""
from enforcer.types import Severity, Needs, RuleType, Match, FileContext, LLMConsequence, LLMConfig, ProviderConfig, ChangeContext
from enforcer.rule import Rule
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter
from enforcer.context import FileContextBuilder
from enforcer.config import Config, load_config
from enforcer.llm import LLMExecutor
from enforcer.fix import apply_fixes, FixResult
from enforcer.ignore import load_enforcerignore, is_ignored

__all__ = [
    "ChangeContext", "Config", "FileContext", "FileContextBuilder",
    "FixResult", "LLMConfig", "LLMConsequence", "LLMExecutor",
    "Match", "Needs", "ProviderConfig", "Reporter", "Rule", "RuleRunner",
    "RuleType", "Severity", "apply_fixes", "is_ignored", "load_config",
    "load_enforcerignore",
]
