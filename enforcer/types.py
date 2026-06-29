"""Core type definitions: Severity, Needs, Match, FileContext, LLMConsequence, ChangeContext."""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

class RuleType(Enum):
    """Whether a rule operates on file contents (per-file) or git metadata (once per run)."""
    CONTENT = "content"
    METADATA = "metadata"

# ponytail: higher = more severe. ERROR > WARN > INFO. Used by RuleRunner for min_severity filtering.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.ERROR: 3,
    Severity.WARN: 2,
    Severity.INFO: 1,
}

# ponytail: lower = sorts first in reporter output. Errors lead, info trails.
SEVERITY_SORT_ORDER: dict[Severity, int] = {
    Severity.ERROR: 0,
    Severity.WARN: 1,
    Severity.INFO: 2,
}

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
    fix_applied: str = ""
    # ponytail: attached by Rule.check() so AST predicates can access the file's AST. Not set for matches created outside Rule.check().
    file_ctx: Any = None

@dataclass
class FileContext:
    """Per-file context: raw text, optional AST, and cross-file read results. Built once, reused by all matchers."""
    path: str
    raw: str | None = None
    ast: object | None = None
    changed_lines: set[int] | None = None
    status: str = "modified"  # "added" | "modified" | "deleted" | "renamed"

@dataclass
class LLMConsequence:
    """Declares an LLM review that fires when a rule's deterministic check fails. One call per file+consequence."""
    provider: str
    model: str
    prompt: str
    timeout: int = 30


@dataclass
class ChangeContext:
    """Carries the change metadata: commit message, branch, and file event lists.
    Stored in shared_ctx["__change__"]. METADATA-phase and finalizer matchers read it."""
    commit_msg: str = ""
    branch: str = ""
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)

    @property
    def created_dirs(self) -> set[str]:
        """Set of parent directories of created files ("" for root-level files)."""
        # ponytail: approximate — dir listed if any child file created. Exact dir-level needs git tree diff, add when needed.
        return {self._dir_of(f) for f in self.created if f}

    @property
    def deleted_dirs(self) -> set[str]:
        """Set of parent directories of deleted files ("" for root-level files)."""
        # ponytail: approximate — dir listed if any child file deleted. Exact dir-level needs git tree diff, add when needed.
        return {self._dir_of(f) for f in self.deleted if f}

    @staticmethod
    def _dir_of(f: str) -> str:
        """Return parent dir of path, "" for root-level ("." → "")."""
        d = str(Path(f).parent)
        return "" if d == "." else d
