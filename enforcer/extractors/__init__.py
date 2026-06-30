"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys

__all__ = ["Extractor", "EnvFileKeys"]
