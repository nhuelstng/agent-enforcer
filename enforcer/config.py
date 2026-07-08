"""Config loading: loads from .py file or package, extracts RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG."""
from __future__ import annotations
import importlib
import importlib.util
import os
import sys
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
            default_provider=raw.get("default_provider", ""),
            default_model=raw.get("default_model", ""),
            concurrency=raw.get("concurrency", 5),
            timeout=raw.get("timeout", 30),
            providers=providers,
        )
    return LLMConfig()

def load_config(config_path: str) -> Config:
    """Load config from a .py file path or a package name. Extracts RULES, WORKSPACE, SEVERITY_ACTIONS, LLM_CONFIG.

    If config_path ends in .py or contains a path separator, treat it as a file path
    (spec_from_file_location). Otherwise, treat it as an importable package/module name
    (importlib.import_module).
    """
    if config_path.endswith(".py") or "/" in config_path or os.sep in config_path:
        # Use a dedicated module name (not "enforcer_config") so loading a
        # file-style config never shadows a real `enforcer_config` package that
        # other code — or a later load — imports by name.
        spec = importlib.util.spec_from_file_location("enforcer_user_config", config_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load config from {config_path}")
        module = importlib.util.module_from_spec(spec)
        # Register before exec so dataclasses / typing resolve annotations against a
        # module present in sys.modules (matches importlib's documented usage) —
        # otherwise a @dataclass matcher defined in the config can fail to build.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        # A package-style config (e.g. "enforcer_config") lives at the repo root;
        # ensure the cwd is importable so `enforcer check` works without callers
        # having to export PYTHONPATH=. themselves.
        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.insert(0, cwd)
        module = importlib.import_module(config_path)

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
