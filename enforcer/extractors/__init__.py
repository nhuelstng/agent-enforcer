"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys

__all__ = ["Extractor", "EnvFileKeys", "TerraformBlockKeys"]
