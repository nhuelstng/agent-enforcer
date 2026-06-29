"""Config loading: executes enforcer_config.py as a module, extracts RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG."""
from __future__ import annotations
import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any
from enforcer.types import Severity, LLMConfig, ProviderConfig

@dataclass
class Config:
    """Loaded configuration: rules, workspace, severity_actions, llm_config."""
    rules: list = field(default_factory=list)
    workspace: str = "."
    severity_actions: dict = field(default_factory=dict)
    llm_config: LLMConfig = field(default_factory=LLMConfig)

def _coerce_llm_config(raw: Any) -> LLMConfig:
    """Coerce LLM_CONFIG from enforcer_config.py into an LLMConfig object.

    Accepts: LLMConfig (pass-through), dict (converted), or None (default)."""
    if isinstance(raw, LLMConfig):
        return raw
    if isinstance(raw, dict):
        providers_raw = raw.get("providers", {})
        providers = {
            name: ProviderConfig(**cfg) if isinstance(cfg, dict) else cfg
            for name, cfg in providers_raw.items()
        }
        return LLMConfig(
            default_provider=raw.get("default_provider", "custom"),
            default_model=raw.get("default_model", ""),
            concurrency=raw.get("concurrency", 5),
            timeout=raw.get("timeout", 30),
            providers=providers,
        )
    return LLMConfig()

def load_config(config_path: str) -> Config:
    """Load enforcer_config.py by executing it as a module. Extracts RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG attributes."""
    spec = importlib.util.spec_from_file_location("enforcer_config", config_path)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load config from {config_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return Config(
        rules=getattr(module, "RULES", []),
        workspace=getattr(module, "WORKSPACE", "."),
        severity_actions=getattr(module, "SEVERITY_ACTIONS", {
            Severity.ERROR: "block",
            Severity.WARN: "print",
            Severity.INFO: "hint",
        }),
        llm_config=_coerce_llm_config(getattr(module, "LLM_CONFIG", LLMConfig())),
    )
