"""FileContextBuilder: parse-once cache. Builds FileContext per file, reuses across rules."""
from __future__ import annotations
import os
from typing import Protocol, runtime_checkable
from enforcer.types import FileContext, Needs
from enforcer.matcher_tree import iter_matchers
from enforcer.parsers.language import language_for_path
from enforcer.parsers.tree_sitter import parse as ts_parse
from enforcer.glob_util import glob_match as _glob_match


def _rule_matches_path(path: str, rule) -> bool:
    """True if a rule's file_globs include the path and its exclude_globs don't."""
    if not any(_glob_match(path, glob) for glob in rule.file_globs):
        return False
    return not any(_glob_match(path, pat) for pat in rule.exclude_globs)


def _rule_needs(rule) -> set[Needs]:
    """Collect the declared Needs of every matcher in a rule's tree."""
    return {n for m in iter_matchers(rule.matchers) if (n := getattr(m, "needs", None))}


@runtime_checkable
class ContextBuilderProtocol(Protocol):
    """Public contract for context builders: build FileContext, aggregate needs, clear cache."""
    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext:
        """Return the FileContext for a path, populating AST if needed."""
        ...
    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate the Needs of all rules whose globs match the path."""
        ...
    def clear_cache(self) -> None:
        """Drop all cached FileContexts."""
        ...


class FileContextBuilder(ContextBuilderProtocol):
    """Builds and caches FileContext objects. Each file is read once; AST is populated lazily when needed.

    The tree-sitter parser is injected (defaulting to the real one) so tests can drive
    the parse-once cache with a fake parser instead of monkeypatching module state."""
    def __init__(self, rules: list, workspace: str = ".", parser=ts_parse):
        self.rules = rules
        self.workspace = workspace
        self._parse = parser
        self._cache: dict[str, FileContext] = {}

    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext:
        """Return FileContext for path. Uses cache. If force_needs is set, ensures AST is populated."""
        cached = self._cache.get(path)
        needs = force_needs or self.needs_for_file(path, self.rules)
        ast_need = self._ast_need(needs)

        if cached:
            self._populate_cached_ast(cached, ast_need)
            return cached

        full_path = os.path.join(self.workspace, path) if self.workspace else path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except (IOError, OSError, UnicodeDecodeError):
            return FileContext(path=path, raw=None)

        ctx = FileContext(path=path, raw=raw)
        if ast_need:
            ctx.ast = self._parse(raw, ast_need)
        self._cache[path] = ctx
        return ctx

    @staticmethod
    def _ast_need(needs: set[Needs]) -> Needs | None:
        """Return the first AST need from the set, or None."""
        for n in needs:
            if n in (Needs.AST_TS, Needs.AST_PY, Needs.AST_CSS, Needs.AST_GO, Needs.AST_CSHARP):
                return n
        return None

    def _populate_cached_ast(self, cached: FileContext, ast_need: Needs | None) -> None:
        """Populate AST on a cached context if needed and raw is available."""
        if not ast_need or cached.ast is not None:
            return
        if cached.raw is not None:
            cached.ast = self._parse(cached.raw, ast_need)

    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate all Needs from rules whose file_globs match this path."""
        needs: set[Needs] = set()
        for rule in rules:
            if _rule_matches_path(path, rule):
                needs |= _rule_needs(rule)
        return needs

    def clear_cache(self) -> None:
        """Clear the FileContext cache."""
        self._cache.clear()
