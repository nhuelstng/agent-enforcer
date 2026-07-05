"""CanonicalImportMatcher: enforces symbols are imported from their canonical module."""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs


@dataclass
class CanonicalImportMatcher:
    """Enforces that symbols are imported from their canonical module, not re-exporting modules.

    What:       flags `from <module> import <symbol>` when <symbol> is in the canonical map
                and <module> is not the canonical source; emits one Match per non-canonical symbol
    Ignores:    imports from the canonical module itself; symbols not in the canonical map;
                `import X` (non-from) statements; files with no AST; relative imports
    Basis:      AST_PY (walks import_from_statement nodes, extracts module + imported names)
    shared_ctx: none (defensive default only)
    """
    canonical: dict[str, str]
    needs: Needs = Needs.AST_PY

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Walk AST for import_from_statement nodes, flag non-canonical imports. Returns list of Match."""
        if not file_ctx.ast:
            return []
        from enforcer.parsers.ast_utils import walk_ast, node_text

        matches: list[Match] = []
        root = file_ctx.ast.root_node
        for node in walk_ast(root):
            if node.type != "import_from_statement":
                continue
            module, names = self._extract_module_and_names(node, node_text)
            if module is None or not names:
                continue
            for name in self._non_canonical_names(module, names):
                matches.append(self._build_match(file_ctx.path, node, name, module))
        return matches

    def _non_canonical_names(self, module: str, names: list[str]) -> list[str]:
        """Return names imported from a non-canonical module."""
        result: list[str] = []
        for name in names:
            canonical_module = self.canonical.get(name)
            if canonical_module is not None and module != canonical_module:
                result.append(name)
        return result

    def _build_match(self, file_path: str, node, name: str, module: str) -> Match:
        """Build a Match for a non-canonical import symbol."""
        canonical_module = self.canonical.get(name, "")
        return Match(
            file=file_path,
            line=node.start_point[0] + 1,
            column=node.start_point[1] + 1,
            matched_value=f"{name} (from {module}, should be from {canonical_module})",
        )

    @staticmethod
    def _extract_module_and_names(node, node_text) -> tuple[str | None, list[str]]:
        """Extract module path and imported names from an import_from_statement node.

        Handles multi-name imports like `from enforcer.rule import Rule, _glob_match`
        and aliased imports like `from enforcer.rule import _glob_match as gm`.
        Follows the same pattern as ImportGraphBuilder._collect_from_import.
        """
        children = node.children
        dotted_names = [c for c in children if c.type == "dotted_name"]
        relative = [c for c in children if c.type == "relative_import"]
        if relative or not dotted_names:
            return None, []

        module = node_text(dotted_names[0])
        if isinstance(module, bytes):
            module = module.decode()

        imported_nodes = dotted_names[1:] + [c for c in children if c.type == "aliased_import"]
        if not imported_nodes:
            return module, []

        names: list[str] = []
        for name_node in imported_nodes:
            resolved = CanonicalImportMatcher._resolve_name_node(name_node)
            if resolved is None:
                continue
            name = node_text(resolved)
            if isinstance(name, bytes):
                name = name.decode()
            names.append(name)
        return module, names

    @staticmethod
    def _resolve_name_node(name_node):
        """Resolve an imported name node, unwrapping aliased_import wrappers. Returns dotted_name node or None."""
        if name_node.type != "aliased_import":
            return name_node
        return next((cc for cc in name_node.children if cc.type == "dotted_name"), None)
