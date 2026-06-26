from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable

class Severity(Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"

class Needs(Enum):
    RAW = "raw"
    AST_TS = "ast_ts"
    AST_PY = "ast_py"
    AST_CSS = "ast_css"

@dataclass
class Match:
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
    path: str
    raw: str | None = None
    ast: object | None = None

@dataclass
class LLMConsequence:
    provider: str
    model: str
    prompt: str
    timeout: int = 30
