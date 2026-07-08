"""CssCustomPropertyDeclMatcher: flags CSS custom-property declarations by name prefix.

Confines token *definitions* to one place. A design token declared under a
governed prefix (`--color-*`, `--space-*`, … — supplied via `prefixes`) may live
only where the rule's file_globs / exclude_globs allow; a second, conflicting
definition elsewhere is flagged. References (`var(--token)`) are never touched —
only left-hand-side declarations.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.css_utils import iter_declarations, property_name


@dataclass
class CssCustomPropertyDeclMatcher:
    """Flags a CSS custom-property *declaration* whose name matches a governed prefix.

    What:       flags a declaration whose property_name starts with one of `prefixes`
                (governed design-token custom properties that belong to a single
                definition site)
    Ignores:    files with no CSS AST; empty `prefixes` (no-op); non-governed custom
                properties; token references (var(--…))
    Basis:      AST_CSS (walks file_ctx.ast declaration nodes)
    shared_ctx: none (defensive default only)
    """
    prefixes: tuple = field(default_factory=tuple)
    needs: Needs = Needs.AST_CSS

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag governed token declarations found in this file. Returns list of Match."""
        if not file_ctx.ast or not self.prefixes:
            return []
        matches: list[Match] = []
        for decl in iter_declarations(file_ctx.ast.root_node):
            prop = property_name(decl)
            if prop.startswith(self.prefixes):
                matches.append(Match(
                    file=file_ctx.path,
                    line=decl.start_point[0] + 1,
                    column=decl.start_point[1] + 1,
                    matched_value=prop,
                ))
        return matches
