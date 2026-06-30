"""YamlKeys: extracts top-level keys of a YAML mapping (lazy PyYAML import)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class YamlKeys:
    """Extracts top-level keys of a YAML mapping. Lists and scalars return {}.
    PyYAML imported lazily — users not using this extractor pay no dependency cost.
    Designed for flat config (docker-compose service env, GitHub Actions inputs/outputs)."""
    # PyYAML is an optional dependency, required only when using YamlKeys.
    # Raising ImportError surfaces missing dep instead of false-positive matches downstream.
    def extract(self, raw: str) -> set[str]:
        """Parse YAML and return top-level mapping keys.

        Returns empty set for non-mappings (lists, scalars) or malformed YAML.
        Raises ImportError if PyYAML is not installed.
        """
        try:
            import yaml  # lazy: avoid hard PyYAML dep for non-YAML users
        except ImportError:
            raise ImportError(
                "PyYAML is required for YamlKeys extractor. "
                "Install it with: pip install PyYAML"
            )
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
