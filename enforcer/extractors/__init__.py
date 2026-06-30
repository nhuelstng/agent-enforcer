"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys
from enforcer.extractors.json_keys import JsonKeys
from enforcer.extractors.yaml_keys import YamlKeys

__all__ = ["Extractor", "EnvFileKeys", "TerraformBlockKeys", "JsonKeys", "YamlKeys"]
