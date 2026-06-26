from __future__ import annotations
from enforcer.types import Needs

def parse(source: str, needs: Needs):
    try:
        import tree_sitter as ts
    except ImportError:
        return None

    language_map = {
        Needs.AST_TS: _get_ts_language,
        Needs.AST_PY: _get_py_language,
        Needs.AST_CSS: _get_css_language,
    }

    lang_func = language_map.get(needs)
    if not lang_func:
        return None

    language = lang_func()
    if not language:
        return None

    try:
        parser = ts.Parser(language)
    except TypeError:
        parser = ts.Parser()
        parser.language = language
    tree = parser.parse(bytes(source, "utf-8"))
    return tree

def _get_ts_language():
    try:
        import tree_sitter as ts
        import tree_sitter_typescript as ts_ts
        return ts.Language(ts_ts.language_typescript())
    except Exception:
        return None

def _get_py_language():
    try:
        import tree_sitter as ts
        import tree_sitter_python as ts_py
        return ts.Language(ts_py.language())
    except Exception:
        return None

def _get_css_language():
    try:
        import tree_sitter as ts
        import tree_sitter_css as ts_css
        return ts.Language(ts_css.language())
    except Exception:
        return None
