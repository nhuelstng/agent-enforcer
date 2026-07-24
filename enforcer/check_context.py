"""CheckContext: the typed, single-owner container passed to every matcher's find().

Replaces the ad-hoc shared-context dict of magic-string slots. It *is* a dict, so the
per-file read-target cache, matcher scratch keys, and every existing mapping access keep
working — but the well-known slots (rules, workspace, rendered doc, change metadata, LLM
state, import graph) are reached through the typed properties defined here. The contract
lives in this one class instead of being spelled out as string literals across the writers
(check_runner, runner) and the readers (the import-graph, doc-sync, and LLM matchers).

Layout: reserved "__…__" keys hold the well-known slots (behind the properties); every
other key is a read-target path mapped to its FileContext.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from enforcer.types import FileContext, ChangeContext, LLMConfig

if TYPE_CHECKING:
    from enforcer.rule import Rule

_RULES = "__rules__"
_WORKSPACE = "__workspace__"
_RENDERED_DOC = "__rendered_doc__"
_CHANGE = "__change__"
_LLM_ENABLED = "__llm_enabled__"
_LLM_CONFIG = "__llm_config__"
_ALL_FILES = "__all_files__"
_IMPORT_GRAPH = "__import_graph__"
_IMPORT_LINES = "__import_lines__"


class CheckContext(dict):
    """Typed view over the per-run shared context. See the module docstring."""

    def __init__(self, *, rules: "list[Rule] | None" = None, workspace: str = ".",
                 rendered_doc: str = "", change: "ChangeContext | None" = None,
                 llm_enabled: bool = True, llm_config: "LLMConfig | None" = None,
                 all_files: bool = False) -> None:
        super().__init__()
        self[_RULES] = rules if rules is not None else []
        self[_WORKSPACE] = workspace
        self[_RENDERED_DOC] = rendered_doc
        self[_CHANGE] = change
        self[_LLM_ENABLED] = llm_enabled
        self[_LLM_CONFIG] = llm_config
        self[_ALL_FILES] = all_files

    @classmethod
    def of(cls, shared_ctx) -> "CheckContext":
        """Return shared_ctx as a CheckContext.

        Pass-through when it already is one (so identity — and any matcher scratch it
        holds — is preserved); otherwise a typed view over the given mapping's entries
        (empty for None). Lets matchers read typed slots while a test still hands in a
        plain dict."""
        if isinstance(shared_ctx, cls):
            return shared_ctx
        view = cls.__new__(cls)
        dict.__init__(view, shared_ctx or {})
        return view

    # --- well-known slots: read-only ---
    @property
    def rules(self) -> list:
        """The full rule set for this run."""
        return self.get(_RULES, [])

    @property
    def workspace(self) -> str:
        """The workspace root path."""
        return self.get(_WORKSPACE, ".")

    @property
    def rendered_doc(self) -> str:
        """The freshly rendered conventions doc (compared by DocSyncMatcher)."""
        return self.get(_RENDERED_DOC, "")

    @property
    def import_graph(self) -> dict:
        """{source_path: set[target_path]} — empty when no import-graph consumer ran."""
        return self.get(_IMPORT_GRAPH, {})

    @property
    def import_lines(self) -> dict:
        """{source_path: {target_path: 1-based import line}}."""
        return self.get(_IMPORT_LINES, {})

    # --- well-known slots: read/write ---
    @property
    def change(self) -> "ChangeContext | None":
        """The change metadata (commit message, branch, file event lists)."""
        return self.get(_CHANGE)

    @change.setter
    def change(self, value: "ChangeContext | None") -> None:
        """Set the change metadata for this run."""
        self[_CHANGE] = value

    @property
    def llm_enabled(self) -> bool:
        """Whether LLM matchers/consequences may call out this run."""
        return self.get(_LLM_ENABLED, True)

    @llm_enabled.setter
    def llm_enabled(self, value: bool) -> None:
        """Set whether LLM calls are enabled this run."""
        self[_LLM_ENABLED] = value

    @property
    def llm_config(self) -> "LLMConfig | None":
        """The resolved LLM configuration for this run."""
        return self.get(_LLM_CONFIG)

    @llm_config.setter
    def llm_config(self, value: "LLMConfig | None") -> None:
        """Set the resolved LLM configuration for this run."""
        self[_LLM_CONFIG] = value

    @property
    def all_files(self) -> bool:
        """True on a full-repo scan (--all), where diff_only rules also fire."""
        return self.get(_ALL_FILES, False)

    @all_files.setter
    def all_files(self, value: bool) -> None:
        """Set the full-repo-scan flag for this run."""
        self[_ALL_FILES] = value

    def set_import_graph(self, graph: dict, lines: dict) -> None:
        """Record the pre-built import graph and its per-edge line attribution."""
        self[_IMPORT_GRAPH] = graph
        self[_IMPORT_LINES] = lines

    # --- per-file read-target cache ---
    def cache_file(self, path: str, file_ctx: FileContext) -> None:
        """Cache a read-target FileContext under its path key."""
        self[path] = file_ctx

    def file_ctx(self, path: str) -> "FileContext | None":
        """Return the cached FileContext for a path, or None. O(1)."""
        value = self.get(path)
        return value if isinstance(value, FileContext) else None

    @property
    def files(self) -> dict:
        """The cached read-target FileContexts keyed by path.

        Reserved "__…__" slots and any non-FileContext value are excluded, so
        cross-file matchers iterate real read targets without a prefix guard."""
        return {k: v for k, v in self.items()
                if not k.startswith("__") and isinstance(v, FileContext)}
