from __future__ import annotations
import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any
from enforcer.types import Severity

@dataclass
class Config:
    rules: list = field(default_factory=list)
    workspace: str = "."
    severity_actions: dict = field(default_factory=dict)
    llm_config: dict = field(default_factory=dict)

def load_config(config_path: str) -> Config:
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
        llm_config=getattr(module, "LLM_CONFIG", {
            "concurrency": 5,
            "timeout": 30,
        }),
    )
