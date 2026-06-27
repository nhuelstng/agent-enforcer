"""FileContextBuilder: parse-once cache. Builds FileContext per file, reuses across rules."""
from __future__ import annotations
import os
from enforcer.types import FileContext, Needs
from enforcer.parsers.language import language_for_path
from enforcer.parsers.tree_sitter import parse as ts_parse

class FileContextBuilder:
    """Builds and caches FileContext objects. Each file is read once; AST is populated lazily when needed."""
    def __init__(self, rules: list, workspace: str = "."):
        self.rules = rules
        self.workspace = workspace
        self._cache: dict[str, FileContext] = {}

    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext:
        """Return FileContext for path. Uses cache. If force_needs is set, ensures AST is populated."""
        cached = self._cache.get(path)
        needs = force_needs or self.needs_for_file(path, self.rules)

        ast_need = None
        for n in needs:
            if n in (Needs.AST_TS, Needs.AST_PY, Needs.AST_CSS):
                ast_need = n
                break

        if cached:
            if ast_need and cached.ast is None:
                if cached.raw:
                    cached.ast = ts_parse(cached.raw, ast_need)
            return cached

        full_path = os.path.join(self.workspace, path) if self.workspace else path
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except (IOError, OSError):
            return FileContext(path=path, raw=None)

        ctx = FileContext(path=path, raw=raw)

        if ast_need:
            ctx.ast = ts_parse(raw, ast_need)

        self._cache[path] = ctx
        return ctx

    def needs_for_file(self, path: str, rules: list) -> set[Needs]:
        """Aggregate all Needs from rules whose file_globs match this path."""
        from enforcer.rule import _glob_match
        needs: set[Needs] = set()
        for rule in rules:
            if any(_glob_match(path, glob) for glob in rule.file_globs):
                if not any(_glob_match(path, pat) for pat in rule.exclude_globs):
                    for matcher in rule.matchers:
                        if hasattr(matcher, "needs") and matcher.needs:
                            needs.add(matcher.needs)
        return needs

    def clear_cache(self):
        self._cache.clear()
