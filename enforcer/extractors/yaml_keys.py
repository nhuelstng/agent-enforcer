"""YamlKeys: extracts top-level keys of a YAML mapping (lazy PyYAML import)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class YamlKeys:
    """Extracts top-level keys of a YAML mapping. Lists and scalars return {}.
    PyYAML imported lazily — users not using this extractor pay no dependency cost.
    Designed for flat config (docker-compose service env, GitHub Actions inputs/outputs)."""
    # ponytail: silent no-op if PyYAML absent; add hard dep if YAML sync becomes core use case
    def extract(self, raw: str) -> set[str]:
        """Parse YAML and return top-level mapping keys. Returns empty set for non-mappings or missing PyYAML."""
        try:
            import yaml  # lazy: avoid hard PyYAML dep for non-YAML users
        except ImportError:
            return set()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
