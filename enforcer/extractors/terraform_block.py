"""TerraformBlockKeys: extracts key names from a named Terraform block."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class TerraformBlockKeys:
    """Extracts key names from a named Terraform block (e.g. 'app_environment = { ... }').
    Finds the block by name via regex, walks its body by brace-depth counting,
    extracts 'KEY =' or '"KEY" =' assignments. Block must be top-level
    (depth 1 within the block). Nested blocks are skipped."""
    block_name: str

    def extract(self, raw: str) -> set[str]:
        """Extract uppercase key names from the named block. Returns empty set if block missing."""
        pattern = rf"\b{re.escape(self.block_name)}\s*=\s*\{{"
        m = re.search(pattern, raw)
        if not m:
            return set()
        depth = 0
        body_chars: list[str] = []
        for ch in raw[m.end() - 1:]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            if depth == 1:
                body_chars.append(ch)
        keys: set[str] = set()
        for line in "".join(body_chars).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            km = re.match(r'"?([A-Z][A-Z0-9_]*)"?\s*=', s)
            if km:
                keys.add(km.group(1))
        return keys
