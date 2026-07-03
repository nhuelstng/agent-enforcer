"""TerraformBlockKeys: extracts key names from a named Terraform block."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class TerraformBlockKeys:
    """Extracts key names from a named Terraform block (e.g. 'app_environment = { ... }').
    Finds the block by name via regex, walks its body by brace-depth counting,
    extracts 'KEY =' or '"KEY" =' assignments. Block must be top-level
    (depth 1 within the block). Nested blocks are skipped."""
    block_name: str

    def extract(self, raw: str) -> set[str]:
        """Extract uppercase key names from the named block. Returns empty set if block missing."""
        pattern = rf"\b{re.escape(self.block_name)}\s*=\s*\{{"
        m = re.search(pattern, raw)
        if not m:
            return set()
        body = _extract_block_body(raw[m.end() - 1:])
        return _parse_block_keys(body)


def _extract_block_body(source: str) -> str:
    """Extract the body of a brace-delimited block, tracking string/comment state."""
    # ponytail: heuristic scan, not a full HCL parser. Tracks string literals
    # (double-quoted, backslash-escaped) and # comments so braces inside them
    # don't affect depth. May still be fooled by heredocs or unusual escapes;
    # upgrade path is a real tree-sitter HCL grammar.
    depth = 0
    in_string = False
    escaped = False
    in_comment = False
    body_chars: list[str] = []
    for ch in source:
        if in_comment:
            in_comment = _handle_comment_char(ch, depth, body_chars)
            continue
        if in_string:
            in_string, escaped = _handle_string_char(ch, depth, body_chars, escaped)
            continue
        depth, in_string, in_comment, done = _handle_plain_char(
            ch, depth, body_chars)
        if done:
            break
    return "".join(body_chars)


def _handle_comment_char(ch: str, depth: int, body_chars: list[str]) -> bool:
    """Process a character inside a comment. Returns False (not in comment) on newline."""
    if ch == "\n" and depth == 1:
        body_chars.append(ch)
    return ch != "\n"


def _handle_string_char(ch: str, depth: int, body_chars: list[str], escaped: bool) -> tuple[bool, bool]:
    """Process a character inside a string literal. Returns (in_string, escaped)."""
    if depth == 1:
        body_chars.append(ch)
    if escaped:
        return False, False
    if ch == "\\":
        return True, True
    if ch == '"':
        return False, False
    return True, False


def _handle_plain_char(ch: str, depth: int, body_chars: list[str]) -> tuple[int, bool, bool, bool]:
    """Process a character outside string/comment. Returns (depth, in_string, in_comment, done)."""
    if ch == "#":
        return depth, False, True, False
    if ch == '"':
        if depth == 1:
            body_chars.append(ch)
        return depth, True, False, False
    if ch == "{":
        return depth + 1, False, False, False
    if ch == "}":
        if depth == 1:
            return 0, False, False, True
        return depth - 1, False, False, False
    if depth == 1:
        body_chars.append(ch)
    return depth, False, False, False


def _parse_block_keys(body: str) -> set[str]:
    """Parse KEY = or "KEY" = assignments from a block body."""
    keys: set[str] = set()
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        km = re.match(r'"?([A-Z][A-Z0-9_]*)"?\s*=', s)
        if km:
            keys.add(km.group(1))
    return keys
