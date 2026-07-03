"""Parser infrastructure: tree-sitter AST parsing and language detection."""
from enforcer.parsers.tree_sitter import parse
from enforcer.parsers.language import language_for_path

__all__ = ["language_for_path", "parse"]
