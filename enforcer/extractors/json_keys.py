"""JsonKeys: extracts top-level keys of a JSON object."""
from __future__ import annotations
import json
from dataclasses import dataclass


@dataclass
class JsonKeys:
    """Extracts top-level keys of a JSON object. Arrays and primitives return {}.
    Designed for flat config objects (package.json, tsconfig.json, .vscode/settings.json)."""
    # ponytail: top-level only; add jsonpath selector if nested sync needed
    def extract(self, raw: str) -> set[str]:
        """Parse JSON and return top-level object keys. Returns empty set for non-objects."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
