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
from enforcer.matchers.canonical_import import CanonicalImportMatcher
from enforcer.matchers.css_custom_property import CssCustomPropertyDeclMatcher
from enforcer.matchers.css_literal_value import CssLiteralValueMatcher
from enforcer.matchers.function_complexity import FunctionComplexityMatcher
from enforcer.matchers.paired_file import PairedFileMatcher
from enforcer.matchers.branch_name import BranchNameMatcher
from enforcer.matchers.commit_message import CommitMessageMatcher
from enforcer.matchers.naming_convention import NamingConventionMatcher
from enforcer.matchers.duplicate_code import DuplicateCodeMatcher
from enforcer.matchers.docstring import DocstringMatcher
from enforcer.matchers.llm_check import LLMMatcher
from enforcer.matchers.doc_sync import DocSyncMatcher
from enforcer.matchers.keyset_sync import KeySetSyncMatcher
from enforcer.matchers.test_coverage import TestCoverageMatcher
from enforcer.matchers.interface_check import InterfaceMatcher
from enforcer.matchers.duplicate_rule_id import DuplicateRuleIdMatcher
from enforcer.matchers.type_hint import TypeHintMatcher
from enforcer.matchers.all_sorted import AllSortedMatcher
from enforcer.matchers.no_module_side_effects import NoModuleSideEffectsMatcher
from enforcer.matchers.constant_naming import ConstantNamingMatcher
from enforcer.matchers.magic_number import MagicNumberMatcher
from enforcer.matchers.architecture import ArchitectureMatcher
from enforcer.matchers.import_cycle import CycleMatcher
from enforcer.matchers.deep_import_barrier import DeepImportBarrierMatcher
from enforcer.matchers.facade_exists import FacadeExistsMatcher
from enforcer.matchers.facade_exposes_interface import FacadeExposesInterfaceMatcher
from enforcer.matchers.invocation import InvocationMatcher
from enforcer.matchers.async_method import AsyncMethodMatcher

__all__ = [
    "AllSortedMatcher",
    "AllowlistMatcher",
    "AlwaysMatcher",
    "ArchitectureMatcher",
    "AsyncMethodMatcher",
    "CanonicalImportMatcher",
    "AstNodeMatcher",
    "BranchNameMatcher",
    "CharCountMatcher",
    "CommentPerFunctionMatcher",
    "CommitMessageMatcher",
    "ConstantNamingMatcher",
    "CssCustomPropertyDeclMatcher",
    "CssLiteralValueMatcher",
    "CycleMatcher",
    "DeepImportBarrierMatcher",
    "DocSyncMatcher",
    "DocstringMatcher",
    "DuplicateCodeMatcher",
    "DuplicateRuleIdMatcher",
    "FacadeExposesInterfaceMatcher",
    "FacadeExistsMatcher",
    "FileExistsMatcher",
    "FunctionComplexityMatcher",
    "ImportMatcher",
    "InterfaceMatcher",
    "InvocationMatcher",
    "KeySetSyncMatcher",
    "LLMMatcher",
    "LineCountMatcher",
    "MagicNumberMatcher",
    "NamingConventionMatcher",
    "NoModuleSideEffectsMatcher",
    "PairedFileMatcher",
    "PathNotMatchingMatcher",
    "RegexMatcher",
    "TestCoverageMatcher",
    "TypeHintMatcher",
]
