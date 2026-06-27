"""Core type definitions: Severity, Needs, Match, FileContext, LLMConsequence."""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable

class Severity(Enum):
    """Convention violation severity level. ERROR blocks commit, WARN blocks unless confirmed, INFO is advisory."""
    ERROR = "error"
    WARN = "warn"
    INFO = "info"

class Needs(Enum):
    """Declares what a matcher needs from the file context (raw text, AST, cross-file reads)."""
    RAW = "raw"
    AST_TS = "ast_ts"
    AST_PY = "ast_py"
    AST_CSS = "ast_css"

@dataclass
class Match:
    """A single rule violation found in a file. Carries location, message, and optional LLM response."""
    file: str
    line: int
    column: int = 0
    message: str = ""
    rule_id: str = ""
    severity: Severity = Severity.WARN
    fix_instruction: str = ""
    llm_response: str = ""
    matched_value: str = ""

@dataclass
class FileContext:
    """Per-file context: raw text, optional AST, and cross-file read results. Built once, reused by all matchers."""
    path: str
    raw: str | None = None
    ast: object | None = None
    changed_lines: set[int] | None = None

@dataclass
class LLMConsequence:
    """Declares an LLM review that fires when a rule's deterministic check fails. One call per file+consequence."""
    provider: str
    model: str
    prompt: str
    timeout: int = 30
