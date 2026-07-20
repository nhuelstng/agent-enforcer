"""FileContextBuilder: parse-once cache. Builds FileContext per file, reuses across rules."""
from __future__ import annotations
import os
from typing import Protocol, runtime_checkable
from enforcer.types import FileContext, Needs
from enforcer.parsers.language import language_for_path
from enforcer.parsers.tree_sitter import parse as ts_parse
from enforcer.glob_util import glob_match as _glob_match


def _collect_needs(matcher, needs: set[Needs]) -> None:
    """Walk combinator tree, collect Needs from all leaf matchers."""
    stack: list = [matcher]
    while stack:
        m = stack.pop()
        if hasattr(m, "matchers") and isinstance(m.matchers, list):
            stack.extend(m.matchers)
        elif hasattr(m, "matcher") and m.matcher is not None:
            stack.append(m.matcher)
        if hasattr(m, "needs") and m.needs:
            needs.add(m.needs)


@runtime_checkable
class ContextBuilderProtocol(Protocol):
    """Public contract for context builders: build FileContext, aggregate needs, clear cache."""
    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext: ...
    def needs_for_file(self, path: str, rules: list) -> set[Needs]: ...
    def clear_cache(self) -> None: ...


class FileContextBuilder(ContextBuilderProtocol):
    """Builds and caches FileContext objects. Each file is read once; AST is populated lazily when needed."""
    def __init__(self, rules: list, workspace: str = "."):
        self.rules = rules
        self.workspace = workspace
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
            ctx.ast = ts_parse(raw, ast_need)
        self._cache[path] = ctx
        return ctx

    @staticmethod
    def _ast_need(needs: set[Needs]) -> Needs | None:
        """Return the first AST need from the set, or None."""
        for n in needs:
            if n in (Needs.AST_TS, Needs.AST_PY, Needs.AST_CSS, Needs.AST_GO, Needs.AST_CSHARP):
                return n
        return None

    @staticmethod
    def _populate_cached_ast(cached: FileContext, ast_need: Needs | None) -> None:
        """Populate AST on a cached context if needed and raw is available."""
        if not ast_need or cached.ast is not None:
            return
        if cached.raw is not None:
            cached.ast = ts_parse(cached.raw, ast_need)

    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate all Needs from rules whose file_globs match this path."""
        needs: set[Needs] = set()
        for rule in rules:
            if not any(_glob_match(path, glob) for glob in rule.file_globs):
                continue
            if any(_glob_match(path, pat) for pat in rule.exclude_globs):
                continue
            for matcher in rule.matchers:
                _collect_needs(matcher, needs)
        return needs

    def clear_cache(self) -> None:
        """Clear the FileContext cache."""
        self._cache.clear()
