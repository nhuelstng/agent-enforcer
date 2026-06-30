"""Extractor protocol: parses raw file text into a set of key strings. Pure function — no I/O."""
from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    """Parses raw file text into a set of key strings. Pure function — no I/O."""
    def extract(self, raw: str) -> set[str]:
        """Parse raw text and return a set of key strings."""
        ...
