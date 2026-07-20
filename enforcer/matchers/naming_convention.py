"""NamingConventionMatcher: walks AST for declarations, checks names against a regex."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs

# ponytail: node types where the name is the first identifier child
_DECL_NODE_TYPES = {
    "function_definition": "function",     # Python def
    "function_declaration": "function",     # TS function + Go func
    "method_definition": "method",          # Python/TS method
    "method_declaration": "method",         # TS method declaration + Go method
    "class_definition": "class",            # Python class
    "class_declaration": "class",           # TS class
    "variable_declaration": "variable",     # TS const/let/var
    # Go: names live on the *_spec nodes inside a declaration wrapper. Target the
    # spec node types directly (e.g. declaration_types=["type_spec"]).
    "type_spec": "type",                    # Go type
    "const_spec": "constant",               # Go const
    "var_spec": "variable",                 # Go var
    "field_declaration": "field",           # Go struct field
    # C#: type and member declarations (class_declaration/method_declaration shared above)
    "interface_declaration": "interface",   # C# interface
    "struct_declaration": "struct",         # C# struct
    "enum_declaration": "enum",             # C# enum
    "record_declaration": "record",         # C# record
    "property_declaration": "property",     # C# property
    "local_function_statement": "function",  # C# local function
    "namespace_declaration": "namespace",   # C# namespace
}

@dataclass
class NamingConventionMatcher:
    """Walks AST for declaration nodes, flags names that don't match the required pattern.
    declaration_types: which node types to check (e.g. ['function_definition', 'class_definition']).
    pattern: regex the declaration name must match. If it doesn't match, the name is flagged.

    What:       flags declaration names (functions/classes/variables per declaration_types) that don't match `pattern`
    Ignores:    files with no parsed AST; declaration node types not in declaration_types; nodes with no extractable identifier; names that match
    Basis:      AST_PY (default; AST_TS when overridden) — walks file_ctx.ast for declaration nodes
    shared_ctx: none (defensive default only)
    """
    declaration_types: list[str]
    pattern: str
    needs: Needs = Needs.AST_PY

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag declaration names that don't match the required regex pattern. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in self._walk(root):
            if node.type not in self.declaration_types or node.type not in _DECL_NODE_TYPES:
                continue
            name = self._extract_name(node)
            if name and not self._compiled.search(name):
                matches.append(Match(
                    file=file_ctx.path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1] + 1,
                    matched_value=name,
                ))
        return matches

    def _extract_name(self, node) -> str:
        # ponytail: name is the first identifier child for most declaration nodes.
        # Go methods and struct fields name themselves with a field_identifier.
        if self.needs == Needs.AST_CSHARP:
            return self._extract_csharp_name(node)
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier", "field_identifier"):
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    @staticmethod
    def _extract_csharp_name(node) -> str:
        """Return a C# declaration's name.

        For members (method/local-function/property/record) the name is the
        identifier immediately preceding the parameter or accessor list, since a
        leading identifier would be the return/element type. For plain type
        declarations (class/interface/struct/enum) the first identifier is the name.
        """
        for idx, child in enumerate(node.children):
            if child.type not in ("parameter_list", "accessor_list"):
                continue
            prev = [c for c in node.children[:idx] if c.type == "identifier"]
            if prev:
                raw = prev[-1].text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        for child in node.children:
            if child.type == "identifier":
                raw = child.text
                return raw.decode() if hasattr(raw, "decode") else str(raw)
        return ""

    def _walk(self, node):
        # ponytail: iterative DFS — avoids RecursionError on deeply nested AST
        stack = [node]
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))
