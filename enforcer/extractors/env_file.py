"""EnvFileKeys: extracts KEY names from env-style 'KEY=VALUE' lines."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EnvFileKeys:
    """Extracts KEY names from env-style 'KEY=VALUE' lines.
    Skips blank lines, comments (#), and lines without '='. Key is the
    substring before the first '=', stripped."""
    def extract(self, raw: str) -> set[str]:
        """Parse env-style text and return the set of KEY names before '='."""
        keys: set[str] = set()
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key = s.split("=", 1)[0].strip()
            if key:
                keys.add(key)
        return keys
