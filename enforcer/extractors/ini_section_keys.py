"""IniSectionKeys: extracts keys within a named INI section."""
from __future__ import annotations
import configparser
from dataclasses import dataclass


@dataclass
class IniSectionKeys:
    """Extracts keys within a named INI section. Useful for .editorconfig, .flake8,
    setup.cfg-style configs where keys must stay in sync across files."""
    section: str

    def extract(self, raw: str) -> set[str]:
        """Parse INI text and return keys within the named section. Returns empty set for missing section or malformed input."""
        parser = configparser.ConfigParser()
        try:
            parser.read_string(raw)
        except configparser.Error:
            return set()
        if parser.has_section(self.section):
            return set(parser.options(self.section))
        return set()
