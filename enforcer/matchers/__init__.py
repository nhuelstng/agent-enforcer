"""Matcher implementations: find rule violations in file content. Each matcher declares Needs and implements find()."""
from enforcer.matchers.regex import RegexMatcher
from enforcer.matchers.line_count import LineCountMatcher
from enforcer.matchers.char_count import CharCountMatcher
from enforcer.matchers.path_pattern import PathNotMatchingMatcher
from enforcer.matchers.allowlist import AllowlistMatcher
from enforcer.matchers.ast_node import AstNodeMatcher
from enforcer.matchers.comment_density import CommentPerFunctionMatcher
from enforcer.matchers.always import AlwaysMatcher
from enforcer.matchers.file_exists import FileExistsMatcher
from enforcer.matchers.import_matcher import ImportMatcher
from enforcer.matchers.function_complexity import FunctionComplexityMatcher
from enforcer.matchers.paired_file import PairedFileMatcher
from enforcer.matchers.branch_name import BranchNameMatcher
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.matchers.duplicate_code import DuplicateCodeMatcher

__all__ = [
    "RegexMatcher",
    "LineCountMatcher",
    "CharCountMatcher",
    "PathNotMatchingMatcher",
    "AllowlistMatcher",
    "AstNodeMatcher",
    "CommentPerFunctionMatcher",
    "AlwaysMatcher",
    "FileExistsMatcher",
    "ImportMatcher",
    "FunctionComplexityMatcher",
    "PairedFileMatcher",
    "BranchNameMatcher",
    "CommitMessageMatcher",
    "NamingConventionMatcher",
    "DuplicateCodeMatcher",
]
