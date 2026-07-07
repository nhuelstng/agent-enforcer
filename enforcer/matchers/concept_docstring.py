"""ConceptDocstringMatcher: flags public class/function symbols missing 'What:' docstring section."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import walk_ast, node_text

_WHAT_RE = re.compile(r"^\s*What:\s*\S", re.MULTILINE)
_FUNC_NODE_TYPES = {
    "function_definition", "function_declaration",
    "method_definition", "method_declaration",
}


@dataclass
class ConceptDocstringMatcher:
    """Walks AST for public class/function nodes, flags those whose docstring lacks a 'What:' section.

    What:       flags public class/function symbols whose docstring has no 'What:' section (or no docstring at all)
    Ignores:    private (_-prefixed) symbols; files with no parsed AST; non-class/function nodes
    Basis:      AST_PY (walks file_ctx.ast for class_definition/function_definition nodes, checks docstring + What: regex)
    shared_ctx: none (defensive default only)
    """
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag public symbols missing 'What:' docstring section. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type not in ("class_definition", *_FUNC_NODE_TYPES):
                continue
            name = self._extract_name(node)
            if not name or name.startswith("_"):
                continue
            if not self._has_what_section(node):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    matched_value=name,
                ))
        return matches

    @staticmethod
    def _extract_name(node) -> str:
        """Extract identifier name from a class/function definition node."""
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return ""

    @staticmethod
    def _has_what_section(node) -> bool:
        """Check if the node's docstring contains a 'What:' section."""
        docstring = ConceptDocstringMatcher._docstring_for(node)
        if not docstring:
            return False
        return bool(_WHAT_RE.search(docstring))

    @staticmethod
    def _docstring_for(node) -> str:
        """Extract the first string expression_statement in the node's block, or empty string."""
        block = next((c for c in node.children if c.type == "block"), None)
        if not block or not block.children:
            return ""
        first = block.children[0]
        if first.type != "expression_statement":
            return ""
        string_node = next((gc for gc in first.children if gc.type == "string"), None)
        if string_node is None:
            return ""
        return node_text(string_node).strip("'\"")
