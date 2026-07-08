"""CssLiteralValueMatcher: flags CSS design-property values that are literals, not tokens.

Walks the tree-sitter CSS tree at the `declaration` level and classifies each
declaration by its `(property, value)` pair. A design property (colour, spacing,
radius, font size/weight/family, transition timing — selected via `categories`)
must carry a `var(--token)` reference or a safe keyword, never a hardcoded literal.
Layout properties (display, grid, width, position, …) are never inspected.

Generic CSS knowledge only — the property→category maps, units, keywords and
named-colour set below are universal CSS, not project-specific. Point it at your
component stylesheets with a Rule's file_globs / exclude_globs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs
from enforcer.parsers.ast_utils import node_text
from enforcer.parsers.css_utils import iter_declarations, property_name, value_nodes, descendants

# Colour props where even a bare named colour (plain_value) is a literal.
_COLOR_PROPS_STRICT = {
    "color", "fill", "stroke", "background-color", "outline-color", "caret-color",
    "border-color", "border-top-color", "border-right-color", "border-bottom-color",
    "border-left-color", "text-decoration-color", "column-rule-color", "accent-color",
}
# Shorthands / multi-value props: only literal hex / rgb() / hsl() count (a bare
# keyword like `no-repeat` or `solid` is not a colour).
_COLOR_PROPS_LOOSE = {
    "background", "border", "outline", "box-shadow", "text-shadow",
    "border-top", "border-right", "border-bottom", "border-left",
}
_SPACING_PROPS = {
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "gap", "row-gap", "column-gap", "margin-block", "margin-inline",
    "padding-block", "padding-inline",
}
_RADIUS_PROPS = {
    "border-radius", "border-top-left-radius", "border-top-right-radius",
    "border-bottom-left-radius", "border-bottom-right-radius",
}
_TIMING_PROPS = {"transition-timing-function", "animation-timing-function"}
_FONT_SIZE_PROPS = {"font-size"}
_FONT_WEIGHT_PROPS = {"font-weight"}
_FONT_FAMILY_PROPS = {"font-family"}

# Keywords that are never a hardcoded design value.
_COLOR_KEYWORDS = {
    "inherit", "currentcolor", "transparent", "none", "unset", "initial",
    "revert", "revert-layer",
}
_FONT_FAMILY_KEYWORDS = {"inherit", "initial", "unset", "revert"}
# Length units that must come from a token (layout-relative units are allowed).
_TOKEN_UNITS = {"px", "rem", "em", "pt"}
_RADIUS_UNITS = {"px", "rem", "em", "pt"}  # % allowed (e.g. 50% circles)
_EASING_KEYWORDS = {"linear", "ease", "ease-in", "ease-out", "ease-in-out", "step-start", "step-end"}
_WEIGHT_KEYWORDS = {"bold", "bolder", "lighter"}
_RAW_COLOR_FUNCS = {"rgb", "rgba", "hsl", "hsla"}
_TIMING_FUNCS = {"cubic-bezier", "steps"}

# CSS numeric font-weight range (100–900 in steps of 100).
_MIN_FONT_WEIGHT = 100
_MAX_FONT_WEIGHT = 900

# A common set of CSS named colours (closes the obvious gap for strict colour props).
_NAMED_COLORS = {
    "white", "black", "red", "green", "blue", "yellow", "orange", "purple",
    "gray", "grey", "silver", "gold", "pink", "brown", "cyan", "magenta",
    "navy", "teal", "maroon", "olive", "lime", "aqua", "fuchsia", "coral",
    "salmon", "crimson", "indigo", "violet", "khaki", "beige", "ivory",
    "tan", "turquoise", "orchid", "plum", "lavender", "wheat",
}


def _is_literal_color_node(node) -> bool:
    """True if a node is a hex colour_value or an rgb()/hsl() function name."""
    if node.type == "color_value":
        return True
    return node.type == "function_name" and node_text(node).lower() in _RAW_COLOR_FUNCS


def _has_literal_color(values) -> bool:
    """True if any value node is a hex colour or an rgb()/hsl() call."""
    return any(_is_literal_color_node(d) for v in values for d in descendants(v))


def _is_named_color_node(node) -> bool:
    """True if a node is a bare CSS named colour (white, red, …), not a keyword."""
    if node.type != "plain_value":
        return False
    text = node_text(node).lower()
    return text in _NAMED_COLORS and text not in _COLOR_KEYWORDS


def _has_named_color(values) -> bool:
    """True if any value node is a bare CSS named colour."""
    return any(_is_named_color_node(d) for v in values for d in descendants(v))


def _is_length_node(node, units) -> bool:
    """True if a numeric node carries a unit child in `units` (e.g. px/rem)."""
    if node.type not in ("integer_value", "float_value"):
        return False
    return any(c.type == "unit" and node_text(c).lower() in units for c in node.children)


def _has_length(values, units) -> bool:
    """True if any value node is a numeric length in one of `units`."""
    return any(_is_length_node(d, units) for v in values for d in descendants(v))


def _is_font_weight_node(node) -> bool:
    """True if a node is a numeric weight (100–900) or a weight keyword."""
    if node.type == "plain_value" and node_text(node).lower() in _WEIGHT_KEYWORDS:
        return True
    if node.type != "integer_value" or any(c.type == "unit" for c in node.children):
        return False
    text = node_text(node)
    return text.isdigit() and _MIN_FONT_WEIGHT <= int(text) <= _MAX_FONT_WEIGHT


def _has_font_weight_literal(values) -> bool:
    """True if any value node is a literal font weight."""
    return any(_is_font_weight_node(d) for v in values for d in descendants(v))


def _is_font_family_literal_node(node) -> bool:
    """True if a direct value node names a literal family vs a var()/keyword.

    Inspects only DIRECT value nodes — descending would treat the token name
    inside `var(--font-sans)` (a plain_value) as a bare font name.
    """
    if node.type == "string_value":
        return True
    return node.type == "plain_value" and node_text(node).lower() not in _FONT_FAMILY_KEYWORDS


def _has_font_family_literal(values) -> bool:
    """True if a font-family value is a literal family instead of var()/keyword."""
    return any(_is_font_family_literal_node(v) for v in values)


def _is_timing_node(node) -> bool:
    """True if a node is a cubic-bezier()/steps() call or a bare easing keyword."""
    if node.type == "function_name" and node_text(node).lower() in _TIMING_FUNCS:
        return True
    return node.type == "plain_value" and node_text(node).lower() in _EASING_KEYWORDS


def _has_timing_literal(values) -> bool:
    """True if a timing value is a literal easing instead of var()."""
    return any(_is_timing_node(d) for v in values for d in descendants(v))


def _color_violation(prop, values) -> bool:
    """True if a colour property carries a literal (strict props also flag named colours)."""
    if prop in _COLOR_PROPS_STRICT:
        return _has_literal_color(values) or _has_named_color(values)
    if prop in _COLOR_PROPS_LOOSE:
        return _has_literal_color(values)
    return False


# category -> predicate(property_name, value_nodes) -> is-violation.
_CATEGORY_CHECKS = {
    "color": _color_violation,
    "spacing": lambda p, v: p in _SPACING_PROPS and _has_length(v, _TOKEN_UNITS),
    "radius": lambda p, v: p in _RADIUS_PROPS and _has_length(v, _RADIUS_UNITS),
    "font-size": lambda p, v: p in _FONT_SIZE_PROPS and _has_length(v, _TOKEN_UNITS),
    "font-weight": lambda p, v: p in _FONT_WEIGHT_PROPS and _has_font_weight_literal(v),
    "font-family": lambda p, v: p in _FONT_FAMILY_PROPS and _has_font_family_literal(v),
    "timing": lambda p, v: p in _TIMING_PROPS and _has_timing_literal(v),
}


@dataclass
class CssLiteralValueMatcher:
    """Flags a CSS declaration whose design-property value is a literal instead of a token.

    What:       flags declarations where a design property (colour / spacing / radius /
                font-size / font-weight / font-family / timing-function, per `categories`)
                carries a literal value rather than a var(--token) or a safe keyword
    Ignores:    layout properties; custom-property (--*) declarations; var()/color-mix()
                built from tokens; keywords inherit/currentColor/transparent/none; files
                with no CSS AST; the token-definition dir (via the rule's exclude_globs)
    Basis:      AST_CSS (walks file_ctx.ast declaration nodes)
    shared_ctx: none (defensive default only)
    """
    categories: frozenset = field(default_factory=lambda: frozenset(_CATEGORY_CHECKS))
    needs: Needs = Needs.AST_CSS

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Flag design-property declarations carrying literal values. Returns list of Match."""
        if not file_ctx.ast:
            return []
        matches: list[Match] = []
        for decl in iter_declarations(file_ctx.ast.root_node):
            prop = property_name(decl).lower()
            if prop.startswith("--"):
                continue  # token definitions are the other matcher's job
            if self._is_violation(prop, value_nodes(decl)):
                matches.append(Match(
                    file=file_ctx.path,
                    line=decl.start_point[0] + 1,
                    column=decl.start_point[1] + 1,
                    matched_value=node_text(decl).rstrip(";"),
                ))
        return matches

    def _is_violation(self, prop: str, values) -> bool:
        """True if `prop`'s value is a literal for any active category."""
        return any(
            _CATEGORY_CHECKS[c](prop, values)
            for c in self.categories
            if c in _CATEGORY_CHECKS
        )
