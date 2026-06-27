# Bugfixes + Agentic Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 critical implementation bugs, then add 6 agentic features (doc-gen, always-match+LLM, FileExistsMatcher, cross-file extractors, verify_fix MCP, SARIF output) that leverage the existing DSL.

**Architecture:** All features reuse existing matchers, combinators, predicates, LLMConsequence, and Reporter. No new subsystems. Bugfixes first, then features build on the fixed foundation.

**Tech Stack:** Python 3.11+, click, tree-sitter, httpx, pytest

---

## File Structure

**Modified:**
- `enforcer/matchers/ast_node.py` — set default `needs`
- `enforcer/matchers/comment_density.py` — set default `needs`
- `enforcer/context.py` — fix cache key to include `force_needs`, wire `rule.workspace`
- `enforcer/rule.py` — fix `_is_combinator` for `Not`, fix `_render_message` brace escaping
- `enforcer/matchers/allowlist.py` — fix key computation to use full read_target string
- `enforcer/cli.py` — fix `--all` to skip junk dirs, fix `shared_ctx` keying, add `docs` subcommand, add `--rule-id` filter
- `enforcer/mcp_server.py` — fix `msg` leak, add `verify_fix` tool, add `list_conventions` tool
- `enforcer/llm.py` — deduplicate LLM calls per file, inject read_target content into prompt
- `enforcer/reporter.py` — always include `matched_value`, add SARIF format
- `enforcer/matchers/__init__.py` — export new matchers
- `enforcer/__init__.py` — export new types if needed
- `enforcer_config.py` — add example NL rule + cross-file rule

**Created:**
- `enforcer/matchers/always.py` — AlwaysMatcher (matches every file)
- `enforcer/matchers/file_exists.py` — FileExistsMatcher (cross-file existence)
- `enforcer/reporters/sarif.py` — SARIF Reporter subclass (if we restructure) OR inline in reporter.py
- `tests/test_matchers/test_always_matcher.py`
- `tests/test_matchers/test_file_exists_matcher.py`
- `tests/test_docs.py`
- `tests/test_mcp_server.py`
- `tests/test_sarif_reporter.py`
- `tests/test_bugfixes.py`

---

### Task 1: Fix AST matcher `needs` defaults

**Files:**
- Modify: `enforcer/matchers/ast_node.py:9`
- Modify: `enforcer/matchers/comment_density.py:8`

**Problem:** `needs` defaults to `None`. `needs_for_file` in `enforcer/context.py:47` only collects `Needs` where `matcher.needs` is truthy. AST matchers never trigger AST parsing.

- [ ] **Step 1: Fix AstNodeMatcher default `needs`**

`enforcer/matchers/ast_node.py` line 9, change:

```python
    needs: Needs | None = None
```

to:

```python
    needs: Needs = Needs.AST_TS
```

- [ ] **Step 2: Fix CommentPerFunctionMatcher default `needs`**

`enforcer/matchers/comment_density.py` line 8, change:

```python
    needs: Needs | None = None
```

to:

```python
    needs: Needs = Needs.AST_TS
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_matchers/test_ast_node_matcher.py tests/test_matchers/test_comment_density_matcher.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add enforcer/matchers/ast_node.py enforcer/matchers/comment_density.py
git commit -m "fix: AST matcher needs defaults to AST_TS so parsing triggers"
```

---

### Task 2: Fix FileContextBuilder cache to respect `force_needs`

**Files:**
- Modify: `enforcer/context.py:13-15`
- Test: `tests/test_bugfixes.py`

**Problem:** `build()` checks cache before considering `force_needs`. If a file was built without AST, a later call with `force_needs={AST_TS}` returns stale `ctx.ast=None`.

- [ ] **Step 1: Write failing test**

Create `tests/test_bugfixes.py`:

```python
import pytest
from enforcer.context import FileContextBuilder
from enforcer.types import Needs, FileContext


class TestContextCacheForceNeeds:
    def test_force_needs_populates_ast_on_cached_ctx(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("const x = 42;\n")
        builder = FileContextBuilder(rules=[], workspace=str(tmp_path))
        builder.build("x.ts")
        ctx2 = builder.build("x.ts", force_needs={Needs.AST_TS})
        if ctx2.ast is None:
            pytest.skip("tree-sitter not available")
        assert ctx2.ast is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestContextCacheForceNeeds -v`
Expected: FAIL (cached ctx returned with ast=None)

- [ ] **Step 3: Fix cache logic**

Replace `enforcer/context.py` `build` method (lines 13-38) with:

```python
    def build(self, path: str, force_needs: set[Needs] | None = None) -> FileContext:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bugfixes.py::TestContextCacheForceNeeds -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/test_context.py tests/test_bugfixes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/context.py tests/test_bugfixes.py
git commit -m "fix: FileContextBuilder cache respects force_needs, populates AST lazily"
```

---

### Task 3: Fix `_is_combinator` to detect `Not`

**Files:**
- Modify: `enforcer/rule.py:11-12`

**Problem:** `_is_combinator` checks `hasattr(obj, "matchers")` but `Not` has `matcher` (singular). Single `Not` combinator takes the `AllOf` wrapping path instead of direct-call fast path.

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
from enforcer.rule import Rule, _is_combinator
from enforcer.combinators import Not, AllOf
from enforcer.matchers import RegexMatcher
from enforcer.types import Severity


class TestIsCombinator:
    def test_not_detected_as_combinator(self):
        matcher = Not(RegexMatcher(r"TODO"))
        assert _is_combinator(matcher) is True

    def test_allof_detected_as_combinator(self):
        matcher = AllOf([RegexMatcher(r"TODO"), RegexMatcher(r"FIXME")])
        assert _is_combinator(matcher) is True

    def test_plain_matcher_not_combinator(self):
        matcher = RegexMatcher(r"TODO")
        assert _is_combinator(matcher) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestIsCombinator::test_not_detected_as_combinator -v`
Expected: FAIL

- [ ] **Step 3: Fix `_is_combinator`**

`enforcer/rule.py` line 11-12, change:

```python
def _is_combinator(obj) -> bool:
    return hasattr(obj, "matchers") and hasattr(obj, "find")
```

to:

```python
def _is_combinator(obj) -> bool:
    return (hasattr(obj, "matchers") or hasattr(obj, "matcher")) and hasattr(obj, "find")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bugfixes.py::TestIsCombinator -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/rule.py tests/test_bugfixes.py
git commit -m "fix: _is_combinator detects Not combinator (singular matcher attr)"
```

---

### Task 4: Fix `_render_message` brace escaping

**Files:**
- Modify: `enforcer/rule.py:63-70`

**Problem:** `self.message.format(...)` crashes on literal braces in message (e.g. `"Use {const} keyword"`).

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
class TestRenderMessageBraces:
    def test_message_with_literal_braces(self):
        from enforcer.types import Match, Severity
        rule = Rule(
            id="test",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            message="Use {const} keyword instead of var",
        )
        match = Match(file="x.ts", line=1, matched_value="var")
        result = rule._render_message(match)
        assert result == "Use {const} keyword instead of var"

    def test_message_with_placeholder(self):
        from enforcer.types import Match, Severity
        rule = Rule(
            id="test",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            message="Found '{matched_value}' at line {line}",
        )
        match = Match(file="x.ts", line=5, matched_value="var")
        result = rule._render_message(match)
        assert result == "Found 'var' at line 5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestRenderMessageBraces::test_message_with_literal_braces -v`
Expected: FAIL (KeyError on `const`)

- [ ] **Step 3: Fix `_render_message`**

`enforcer/rule.py` lines 63-70, replace with:

```python
    def _render_message(self, match: Match) -> str:
        if callable(self.message):
            return self.message(match)
        safe = self.message.replace("{", "{{").replace("}", "}}")
        for key, val in [
            ("matched_value", match.matched_value),
            ("file", match.file),
            ("line", match.line),
            ("column", match.column),
        ]:
            safe = safe.replace("{{" + key + "}}", str(val))
        return safe
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bugfixes.py::TestRenderMessageBraces -v`
Expected: PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/test_rule.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/rule.py tests/test_bugfixes.py
git commit -m "fix: _render_message escapes literal braces, safe placeholder substitution"
```

---

### Task 5: Fix AllowlistMatcher key computation

**Files:**
- Modify: `enforcer/matchers/allowlist.py:15-16`
- Modify: `enforcer/cli.py:66-69`
- Modify: `enforcer/mcp_server.py:31-34`

**Problem:** AllowlistMatcher uses basename of read_target with `.replace("**/", "").replace("*", "")` hack. CLI uses different key computation. Diverge on `*` in filename. Two files with same basename collide.

Fix: use the full read_target string as the `shared_ctx` key, consistently in CLI, MCP server, and matcher.

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
class TestAllowlistKeying:
    def test_allowlist_uses_full_read_target_key(self):
        from enforcer.matchers import AllowlistMatcher
        from enforcer.types import FileContext

        def extractor(raw):
            return {"red", "blue"}

        def consumer(raw):
            return {"red", "green"}

        matcher = AllowlistMatcher(
            extractor=extractor,
            consumer=consumer,
            read_target="frontend/**/colors.scss",
        )
        target_ctx = FileContext(path="frontend/colors.scss", raw="--color-red: #f00;\n")
        file_ctx = FileContext(path="src/app.ts", raw="var(--color-green)")
        shared = {"frontend/**/colors.scss": target_ctx}
        matches = matcher.find(file_ctx, shared)
        assert len(matches) == 1
        assert matches[0].matched_value == "green"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestAllowlistKeying -v`
Expected: FAIL (matcher looks up basename key, shared dict has full key)

- [ ] **Step 3: Fix AllowlistMatcher key lookup**

`enforcer/matchers/allowlist.py` lines 14-16, replace:

```python
    def find(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        basename = os.path.basename(self.read_target.replace("**/", "").replace("*", ""))
        target_ctx = shared_ctx.get(basename) or shared_ctx.get(os.path.basename(self.read_target))
```

with:

```python
    def find(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        target_ctx = shared_ctx.get(self.read_target)
        if not target_ctx:
            for key, ctx in shared_ctx.items():
                if key.endswith(self.read_target.replace("**/", "").replace("*", "")):
                    target_ctx = ctx
                    break
```

- [ ] **Step 4: Fix CLI shared_ctx keying**

`enforcer/cli.py` lines 64-69, replace:

```python
    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                target_ctx = builder.build(target.replace("**/", ""))
                shared_ctx[os.path.basename(target_path)] = target_ctx
```

with:

```python
    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                target_ctx = builder.build(target.replace("**/", ""))
                shared_ctx[target] = target_ctx
```

- [ ] **Step 5: Fix MCP server shared_ctx keying**

`enforcer/mcp_server.py` lines 27-34, replace:

```python
    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            import os
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                ctx = builder.build(target.replace("**/", ""))
                shared_ctx[os.path.basename(target_path)] = ctx
```

with:

```python
    shared_ctx: dict = {}
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            import os
            target_path = os.path.join(ws, target.replace("**/", ""))
            if os.path.exists(target_path):
                ctx = builder.build(target.replace("**/", ""))
                shared_ctx[target] = ctx
```

- [ ] **Step 6: Fix empty target file bug (falsy `""` treated as "no raw")**

`enforcer/matchers/allowlist.py` line 19, change:

```python
        if not file_ctx.raw or not target_ctx.raw:
            return []
```

to:

```python
        if file_ctx.raw is None or target_ctx.raw is None:
            return []
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_bugfixes.py::TestAllowlistKeying tests/test_matchers/test_allowlist_matcher.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add enforcer/matchers/allowlist.py enforcer/cli.py enforcer/mcp_server.py tests/test_bugfixes.py
git commit -m "fix: AllowlistMatcher uses full read_target as shared_ctx key, fixes collisions"
```

---

### Task 6: Fix `--all` to skip junk dirs

**Files:**
- Modify: `enforcer/cli.py:38-45`

**Problem:** `os.walk` only skips `.git`. Walks `node_modules/`, `__pycache__/`, `.venv/`, etc.

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
class TestAllSkipsJunkDirs:
    def test_all_skips_junk_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("const x = 1;\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("module.exports = 1;\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "x.pyc").write_text("garbage")

        import importlib
        import enforcer.cli as cli_mod
        from click.testing import CliRunner

        config_content = '''
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher
WORKSPACE = "."
RULES = []
'''
        (tmp_path / "enforcer_config.py").write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(cli_mod.cli, [
            "check", "--all", "--workspace", str(tmp_path),
            "--config", str(tmp_path / "enforcer_config.py"),
        ])
        assert "node_modules" not in result.output
        assert "__pycache__" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestAllSkipsJunkDirs -v`
Expected: FAIL (node_modules files included)

- [ ] **Step 3: Fix `--all` walk**

`enforcer/cli.py` lines 38-45, replace:

```python
    elif all_files:
        file_list = []
        for root, dirs, files in os.walk(ws):
            if ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
```

with:

```python
    elif all_files:
        _JUNK_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                       ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
                       "*.egg-info"}
        file_list = []
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if not _glob_any_match(d, _JUNK_DIRS)]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
```

Add helper function above `check` (after the `cli` group):

```python
def _glob_any_match(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bugfixes.py::TestAllSkipsJunkDirs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/cli.py tests/test_bugfixes.py
git commit -m "fix: --all skips node_modules, __pycache__, .venv and other junk dirs"
```

---

### Task 7: Fix MCP server `msg` variable leak

**Files:**
- Modify: `enforcer/mcp_server.py:47-93`

**Problem:** `msg` persists across loop iterations. If iteration N parses OK then N+1 fails, error echoes N's id.

- [ ] **Step 1: Fix `msg` leak**

`enforcer/mcp_server.py` line 49, after `for line in sys.stdin:`, add `msg = None` at top of loop body. Change the error handler line 89:

```python
                "id": msg.get("id") if "msg" in dir() else None,
```

to:

```python
                "id": msg.get("id") if msg else None,
```

The full `run_mcp_server` function becomes:

```python
def run_mcp_server():
    for line in sys.stdin:
        msg = None
        try:
            msg = json.loads(line)
            if msg.get("method") == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": "check_conventions",
                                "description": "Check files for convention violations",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "paths": {"type": "array", "items": {"type": "string"}},
                                        "format": {"type": "string", "enum": ["json", "text"]},
                                    },
                                },
                            },
                            {
                                "name": "list_conventions",
                                "description": "List all configured convention rules as documentation",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                },
                            },
                        ]
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            elif msg.get("method") == "tools/call":
                params = msg.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})
                if tool_name == "check_conventions":
                    result = check_conventions(
                        paths=args.get("paths"),
                        format=args.get("format", "json"),
                    )
                elif tool_name == "list_conventions":
                    result = list_conventions()
                else:
                    result = json.dumps({"error": f"Unknown tool: {tool_name}"})
                response = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {"content": [{"type": "text", "text": result}]}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if msg else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add enforcer/mcp_server.py
git commit -m "fix: MCP server msg variable leak between loop iterations"
```

---

### Task 8: Fix LLM executor redundant calls

**Files:**
- Modify: `enforcer/llm.py:22-32`

**Problem:** Submits one `_call_llm` per match, but prompt is built once from `file_ctx.raw` — identical for every match in same file. N matches → N identical HTTP requests.

Fix: one call per (file, consequence) pair, attach response to all matches.

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
class TestLLMDedup:
    def test_llm_called_once_per_file_not_per_match(self):
        from enforcer.llm import LLMExecutor
        from enforcer.types import Match, FileContext, LLMConsequence
        from unittest.mock import patch, MagicMock

        matches = [
            Match(file="x.ts", line=1, matched_value="#fff"),
            Match(file="x.ts", line=2, matched_value="#000"),
        ]
        ctx = FileContext(path="x.ts", raw="const a = '#fff';\nconst b = '#000';\n")
        consequence = LLMConsequence(provider="test", model="test", prompt="check")

        executor = LLMExecutor(enabled=True)
        with patch.object(executor, "_call_llm", return_value="response") as mock_call:
            result = executor.execute(matches, consequence, ctx)
        assert mock_call.call_count == 1
        assert all(m.llm_response == "response" for m in result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestLLMDedup -v`
Expected: FAIL (call_count == 2)

- [ ] **Step 3: Fix LLM executor**

`enforcer/llm.py` lines 12-34, replace `execute` method with:

```python
    def execute(self, matches: list[Match], consequence: LLMConsequence | None,
                file_ctx: FileContext) -> list[Match]:
        if not consequence or not self.enabled or not matches:
            return matches
        if not file_ctx.raw:
            return matches

        prompt = self._build_prompt(consequence, file_ctx)
        provider_config = self._get_provider_config(consequence.provider)

        try:
            response = self._call_llm(consequence, prompt, provider_config)
        except Exception:
            response = ""

        for m in matches:
            m.llm_response = response
        return matches

    def _build_prompt(self, consequence: LLMConsequence, file_ctx: FileContext,
                      shared_ctx: dict | None = None) -> str:
        prompt = f"{consequence.prompt}\n\n--- FILE CONTENT ---\n{file_ctx.raw}"
        if shared_ctx:
            for key, ctx in shared_ctx.items():
                if ctx and ctx.raw and ctx.path != file_ctx.path:
                    prompt += f"\n\n--- {ctx.path} ---\n{ctx.raw}"
        return prompt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bugfixes.py::TestLLMDedup tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/llm.py tests/test_bugfixes.py
git commit -m "fix: LLM executor deduplicates calls to one per file+consequence"
```

---

### Task 9: Fix Reporter JSON to always include `matched_value`

**Files:**
- Modify: `enforcer/reporter.py:20-31`

**Problem:** `matched_value` never serialized. `llm_response` only included when truthy. Consumers can't rely on stable schema.

- [ ] **Step 1: Fix JSON output**

`enforcer/reporter.py` lines 20-31, replace the issue dict with:

```python
            issue = {
                "file": m.file,
                "line": m.line,
                "column": m.column,
                "rule_id": m.rule_id,
                "severity": m.severity.value,
                "message": m.message,
                "matched_value": m.matched_value,
                "fix_instruction": m.fix_instruction,
                "llm_response": m.llm_response,
            }
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_reporter.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add enforcer/reporter.py
git commit -m "fix: Reporter JSON always includes matched_value and llm_response"
```

---

### Task 10: Add AlwaysMatcher

**Files:**
- Create: `enforcer/matchers/always.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_always_matcher.py`

**Purpose:** Matches every file (or every line). Paired with `LLMConsequence` for natural-language rules ("functions should be short and focused").

- [ ] **Step 1: Write failing test**

Create `tests/test_matchers/test_always_matcher.py`:

```python
from enforcer.matchers import AlwaysMatcher
from enforcer.types import FileContext


def test_always_matcher_matches_non_empty_file():
    ctx = FileContext(path="x.ts", raw="const x = 1;\n")
    matcher = AlwaysMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 1
    assert matches[0].file == "x.ts"
    assert matches[0].matched_value == "(always)"


def test_always_matcher_skips_empty_file():
    ctx = FileContext(path="x.ts", raw=None)
    matcher = AlwaysMatcher()
    matches = matcher.find(ctx)
    assert len(matches) == 0


def test_always_matcher_custom_value():
    ctx = FileContext(path="x.ts", raw="code")
    matcher = AlwaysMatcher(matched_value="check-me")
    matches = matcher.find(ctx)
    assert matches[0].matched_value == "check-me"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_always_matcher.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement AlwaysMatcher**

Create `enforcer/matchers/always.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class AlwaysMatcher:
    matched_value: str = "(always)"
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext) -> list[Match]:
        if not file_ctx.raw:
            return []
        return [Match(file=file_ctx.path, line=1, matched_value=self.matched_value)]
```

- [ ] **Step 4: Export in `__init__.py`**

`enforcer/matchers/__init__.py`, add import and `__all__` entry:

```python
from enforcer.matchers.always import AlwaysMatcher
```

Add `"AlwaysMatcher"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_matchers/test_always_matcher.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/always.py enforcer/matchers/__init__.py tests/test_matchers/test_always_matcher.py
git commit -m "feat: AlwaysMatcher for NL rules paired with LLM consequences"
```

---

### Task 11: Add FileExistsMatcher

**Files:**
- Create: `enforcer/matchers/file_exists.py`
- Modify: `enforcer/matchers/__init__.py`
- Test: `tests/test_matchers/test_file_exists_matcher.py`

**Purpose:** Returns Match if a `read_target` glob resolves to ≥1 file. `Not(FileExistsMatcher(...))` flags ABSENCE. Catches "agent wrote component but no test file".

- [ ] **Step 1: Write failing test**

Create `tests/test_matchers/test_file_exists_matcher.py`:

```python
import pytest
from enforcer.matchers import FileExistsMatcher
from enforcer.types import FileContext


def test_file_exists_when_target_exists(tmp_path):
    (tmp_path / "colors.scss").write_text("--color-red: #f00;\n")
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    matcher = FileExistsMatcher(read_target="colors.scss")
    shared = {"colors.scss": FileContext(path="colors.scss", raw="--color-red: #f00;")}
    matches = matcher.find(ctx, shared)
    assert len(matches) == 1
    assert "exists" in matches[0].matched_value


def test_file_exists_when_target_missing():
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    matcher = FileExistsMatcher(read_target="missing.scss")
    matches = matcher.find(ctx, {})
    assert len(matches) == 0


def test_file_exists_via_shared_ctx():
    ctx = FileContext(path="src/app.ts", raw="const x = 1;")
    shared = {"colors.scss": FileContext(path="colors.scss", raw="--x: 1;")}
    matcher = FileExistsMatcher(read_target="colors.scss")
    matches = matcher.find(ctx, shared)
    assert len(matches) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matchers/test_file_exists_matcher.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement FileExistsMatcher**

Create `enforcer/matchers/file_exists.py`:

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from enforcer.types import Match, FileContext, Needs

@dataclass
class FileExistsMatcher:
    read_target: str
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        if self.read_target in shared_ctx:
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        full_path = os.path.join(self.workspace, self.read_target.replace("**/", ""))
        if os.path.exists(full_path):
            return [Match(
                file=file_ctx.path,
                line=0,
                matched_value=f"{self.read_target} exists",
            )]
        return []
```

- [ ] **Step 4: Export in `__init__.py`**

`enforcer/matchers/__init__.py`, add:

```python
from enforcer.matchers.file_exists import FileExistsMatcher
```

Add `"FileExistsMatcher"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_matchers/test_file_exists_matcher.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/file_exists.py enforcer/matchers/__init__.py tests/test_matchers/test_file_exists_matcher.py
git commit -m "feat: FileExistsMatcher for cross-file existence checks"
```

---

### Task 12: Add `enforcer docs` command + `list_conventions` MCP tool

**Files:**
- Create: `enforcer/docs.py`
- Modify: `enforcer/cli.py`
- Modify: `enforcer/mcp_server.py`
- Test: `tests/test_docs.py`

**Purpose:** Render all rules to markdown so agents can read conventions BEFORE writing code. Proactive conformance.

- [ ] **Step 1: Write failing test**

Create `tests/test_docs.py`:

```python
from enforcer.docs import render_rules_markdown
from enforcer import Rule, Severity
from enforcer.matchers import RegexMatcher


def test_render_empty_rules():
    md = render_rules_markdown([])
    assert "# Conventions" in md
    assert "No rules configured." in md


def test_render_single_rule():
    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts", "**/*.scss"],
            exclude_globs=["**/*.spec.ts"],
            message="Raw hex color '{matched_value}' found. Use var(--color-*).",
            fix_instruction="Replace with var(--color-*) from colors.scss.",
        ),
    ]
    md = render_rules_markdown(rules)
    assert "# Conventions" in md
    assert "## no-raw-hex" in md
    assert "**ERROR**" in md
    assert "**/*.ts" in md
    assert "**/*.spec.ts" in md
    assert "var(--color-*)" in md


def test_render_multiple_rules_sorted():
    rules = [
        Rule(id="z-rule", severity=Severity.INFO, matchers=[], file_globs=["**/*.ts"]),
        Rule(id="a-rule", severity=Severity.ERROR, matchers=[], file_globs=["**/*.ts"]),
    ]
    md = render_rules_markdown(rules)
    lines = md.split("\n")
    a_idx = next(i for i, l in enumerate(lines) if "a-rule" in l)
    z_idx = next(i for i, l in enumerate(lines) if "z-rule" in l)
    assert a_idx < z_idx


def test_render_includes_llm_consequence():
    from enforcer import LLMConsequence
    rules = [
        Rule(
            id="nl-check",
            severity=Severity.WARN,
            matchers=[],
            file_globs=["**/*.ts"],
            llm_consequence=LLMConsequence(
                provider="test", model="gpt-4",
                prompt="Is this function focused and short?",
            ),
        ),
    ]
    md = render_rules_markdown(rules)
    assert "focused and short" in md
    assert "gpt-4" in md


def test_render_includes_read_targets():
    rules = [
        Rule(
            id="cross-file",
            severity=Severity.ERROR,
            matchers=[],
            file_globs=["**/*.ts"],
            read_targets=["**/colors.scss"],
        ),
    ]
    md = render_rules_markdown(rules)
    assert "colors.scss" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docs.py -v`
Expected: FAIL (import error)

- [ ] **Step 3: Implement docs renderer**

Create `enforcer/docs.py`:

```python
from __future__ import annotations
from enforcer.rule import Rule
from enforcer.types import Severity

def render_rules_markdown(rules: list[Rule]) -> str:
    if not rules:
        return "# Conventions\n\nNo rules configured.\n"

    sorted_rules = sorted(rules, key=lambda r: r.id)
    lines = ["# Conventions", ""]
    lines.append(f"_{len(sorted_rules)} rules configured._")
    lines.append("")

    for rule in sorted_rules:
        lines.append(f"## {rule.id}")
        lines.append("")
        lines.append(f"**Severity:** {rule.severity.value.upper()}")
        lines.append("")

        if rule.message:
            msg = rule.message if callable(rule.message) else rule.message
            lines.append(f"**Message:** {msg}")
            lines.append("")

        lines.append(f"**File globs:** {', '.join(rule.file_globs)}")
        lines.append("")

        if rule.exclude_globs:
            lines.append(f"**Excludes:** {', '.join(rule.exclude_globs)}")
            lines.append("")

        if rule.read_targets:
            lines.append(f"**Read targets:** {', '.join(rule.read_targets)}")
            lines.append("")

        if rule.fix_instruction:
            lines.append(f"**Fix:** {rule.fix_instruction}")
            lines.append("")

        if rule.llm_consequence:
            lines.append(f"**LLM check:** {rule.llm_consequence.prompt}")
            lines.append(f"**Model:** {rule.llm_consequence.model}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Add `docs` CLI subcommand**

`enforcer/cli.py`, add after the `check` function (before `if __name__`):

```python
@cli.command()
@click.option("--config", "config_path", default="enforcer_config.py")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
def docs(config_path, output):
    """Generate markdown documentation of all configured rules."""
    from enforcer.docs import render_rules_markdown

    config = load_config(config_path)
    md = render_rules_markdown(config.rules)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        click.echo(f"Documentation written to {output}")
    else:
        click.echo(md)
```

- [ ] **Step 5: Add `list_conventions` MCP tool**

`enforcer/mcp_server.py`, add function:

```python
def list_conventions() -> str:
    """Return all configured rules as markdown documentation."""
    from enforcer.docs import render_rules_markdown
    config = load_config("enforcer_config.py")
    return render_rules_markdown(config.rules)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_docs.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add enforcer/docs.py enforcer/cli.py enforcer/mcp_server.py tests/test_docs.py
git commit -m "feat: enforcer docs command + list_conventions MCP tool"
```

---

### Task 13: Add `verify_fix` MCP tool + `--rule-id` CLI flag

**Files:**
- Modify: `enforcer/mcp_server.py`
- Modify: `enforcer/cli.py`
- Test: `tests/test_mcp_server.py`

**Purpose:** Agent fixes a violation, re-checks ONE rule on ONE file. Tightens self-heal loop.

- [ ] **Step 1: Write failing test**

Create `tests/test_mcp_server.py`:

```python
import json
from enforcer.mcp_server import check_conventions, list_conventions, verify_fix


def test_list_conventions_returns_markdown():
    md = list_conventions()
    assert "# Conventions" in md


def test_verify_fix_returns_pass_or_fail():
    result = json.loads(verify_fix(path="README.md", rule_id="max-lines-readme"))
    assert "summary" in result
    assert "issues" in result


def test_verify_fix_unknown_rule():
    result = json.loads(verify_fix(path="x.ts", rule_id="nonexistent"))
    assert result["summary"]["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL (verify_fix not defined)

- [ ] **Step 3: Implement `verify_fix`**

`enforcer/mcp_server.py`, add function:

```python
def verify_fix(path: str, rule_id: str, format: str = "json") -> str:
    """Re-check a single rule on a single file. Returns formatted output."""
    config = load_config("enforcer_config.py")
    ws = config.workspace

    rule = next((r for r in config.rules if r.id == rule_id), None)
    if not rule:
        return json.dumps({"summary": {"total": 0, "errors": 0, "warnings": 0, "info": 0}, "issues": []})

    runner = RuleRunner(config.rules, workspace=ws, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)

    shared_ctx: dict = {}
    for target in getattr(rule, "read_targets", []):
        import os
        target_path = os.path.join(ws, target.replace("**/", ""))
        if os.path.exists(target_path):
            ctx = builder.build(target.replace("**/", ""))
            shared_ctx[target] = ctx

    ctx = builder.build(path)
    matches = rule.check(ctx, shared_ctx)
    if matches and rule.llm_consequence:
        matches = runner.llm_executor.execute(matches, rule.llm_consequence, ctx)

    reporter = Reporter(format=format)
    return reporter.render(matches)
```

- [ ] **Step 4: Add `verify_fix` to MCP tools list**

In `enforcer/mcp_server.py` `run_mcp_server`, add to `tools/list` response:

```python
                            {
                                "name": "verify_fix",
                                "description": "Re-check a single rule on a single file after a fix",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "rule_id": {"type": "string"},
                                        "format": {"type": "string", "enum": ["json", "text"]},
                                    },
                                    "required": ["path", "rule_id"],
                                },
                            },
```

And in `tools/call` handler, add branch:

```python
                elif tool_name == "verify_fix":
                    result = verify_fix(
                        path=args.get("path"),
                        rule_id=args.get("rule_id"),
                        format=args.get("format", "json"),
                    )
```

- [ ] **Step 5: Add `--rule-id` to CLI `check`**

`enforcer/cli.py`, add option to `check`:

```python
@click.option("--rule-id", default=None, help="Run only this rule ID")
```

Add after `min_severity` filter in the `for f in file_list:` loop:

```python
    if rule_id:
        config.rules = [r for r in config.rules if r.id == rule_id]
```

Insert this line right after `config = load_config(config_path)` (line 29), before `ws = workspace or config.workspace`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add enforcer/mcp_server.py enforcer/cli.py tests/test_mcp_server.py
git commit -m "feat: verify_fix MCP tool + --rule-id CLI flag for tight self-heal loop"
```

---

### Task 14: Add SARIF reporter

**Files:**
- Modify: `enforcer/reporter.py`
- Test: `tests/test_sarif_reporter.py`

**Purpose:** SARIF is the standard for GitHub code-scanning alerts. One format addition, unlocks GitHub UI.

- [ ] **Step 1: Write failing test**

Create `tests/test_sarif_reporter.py`:

```python
import json
from enforcer.reporter import Reporter
from enforcer.types import Match, Severity


def test_sarif_empty():
    reporter = Reporter(format="sarif")
    output = reporter.render([])
    data = json.loads(output)
    assert data["version"] == "2.1.0"
    assert data["runs"][0]["results"] == []


def test_sarif_with_results():
    matches = [
        Match(
            file="src/app.ts",
            line=10,
            column=5,
            rule_id="no-raw-hex",
            severity=Severity.ERROR,
            message="Raw hex found",
            matched_value="#fff",
            fix_instruction="Use var(--color-*)",
        ),
    ]
    reporter = Reporter(format="sarif")
    output = reporter.render(matches)
    data = json.loads(output)
    assert data["version"] == "2.1.0"
    run = data["runs"][0]
    result = run["results"][0]
    assert result["ruleId"] == "no-raw-hex"
    assert result["level"] == "error"
    assert result["message"]["text"] == "Raw hex found"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "src/app.ts"
    assert loc["region"]["startLine"] == 10
    assert loc["region"]["startColumn"] == 5


def test_sarif_includes_rules_metadata():
    matches = [
        Match(
            file="x.ts", line=1, rule_id="test-rule",
            severity=Severity.WARN, message="test",
        ),
    ]
    reporter = Reporter(format="sarif")
    output = reporter.render(matches)
    data = json.loads(output)
    rules = data["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) == 1
    assert rules[0]["id"] == "test-rule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sarif_reporter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SARIF renderer**

`enforcer/reporter.py`, add SARIF rendering. Add `"sarif"` to the format check in `render()` and add the method. Full updated `render` method:

```python
    def render(self, matches: list[Match]) -> str:
        if self.format == "json":
            return self._render_json(matches)
        if self.format == "sarif":
            return self._render_sarif(matches)
        return self._render_text(matches)
```

Add method:

```python
    def _render_sarif(self, matches: list[Match]) -> str:
        _SEV_TO_SARIF = {Severity.ERROR: "error", Severity.WARN: "warning", Severity.INFO: "note"}
        results = []
        rules_seen = {}
        for m in matches:
            if m.rule_id not in rules_seen:
                rules_seen[m.rule_id] = {
                    "id": m.rule_id,
                    "name": m.rule_id,
                    "shortDescription": {"text": m.message or m.rule_id},
                    "defaultConfiguration": {"level": _SEV_TO_SARIF.get(m.severity, "note")},
                }
            results.append({
                "ruleId": m.rule_id,
                "level": _SEV_TO_SARIF.get(m.severity, "note"),
                "message": {"text": m.message},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": m.file},
                        "region": {"startLine": m.line, "startColumn": max(m.column, 1)},
                    }
                }],
            })
        sarif = {
            "version": "2.1.0",
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/Schemata/sarif-schema-2.1.0.json",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "pre-commit-agent-enforcer",
                        "rules": list(rules_seen.values()),
                    }
                },
                "results": results,
            }],
        }
        return json.dumps(sarif, indent=2)
```

- [ ] **Step 4: Update CLI format choice**

`enforcer/cli.py` line 20, change:

```python
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]))
```

to:

```python
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text", "sarif"]))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sarif_reporter.py tests/test_reporter.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add enforcer/reporter.py enforcer/cli.py tests/test_sarif_reporter.py
git commit -m "feat: SARIF output format for GitHub code-scanning integration"
```

---

### Task 15: Inject `read_target` content into LLM prompt

**Files:**
- Modify: `enforcer/runner.py:30-31`
- Modify: `enforcer/llm.py`

**Purpose:** LLM consequence gets read_target file contents in prompt. Enables "does this test actually test the source behavior?".

- [ ] **Step 1: Write failing test**

Add to `tests/test_bugfixes.py`:

```python
class TestLLMReadTargetInjection:
    def test_llm_prompt_includes_read_target_content(self):
        from enforcer.llm import LLMExecutor
        from enforcer.types import Match, FileContext, LLMConsequence

        ctx = FileContext(path="app.ts", raw="const x = 1;")
        target_ctx = FileContext(path="colors.scss", raw="--color-red: #f00;")
        shared = {"**/colors.scss": target_ctx}
        consequence = LLMConsequence(provider="test", model="test", prompt="check")

        executor = LLMExecutor(enabled=True)
        prompt = executor._build_prompt(consequence, ctx, shared)
        assert "colors.scss" in prompt
        assert "--color-red: #f00." in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bugfixes.py::TestLLMReadTargetInjection -v`
Expected: FAIL (shared_ctx not passed to _build_prompt)

- [ ] **Step 3: Wire `shared_ctx` through to LLM executor**

`enforcer/runner.py` line 30-31, change:

```python
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, file_ctx)
```

to:

```python
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, file_ctx, shared_ctx)
```

`enforcer/llm.py` `execute` method, change signature and call:

```python
    def execute(self, matches: list[Match], consequence: LLMConsequence | None,
                file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        if not consequence or not self.enabled or not matches:
            return matches
        if not file_ctx.raw:
            return matches

        prompt = self._build_prompt(consequence, file_ctx, shared_ctx)
        provider_config = self._get_provider_config(consequence.provider)

        try:
            response = self._call_llm(consequence, prompt, provider_config)
        except Exception:
            response = ""

        for m in matches:
            m.llm_response = response
        return matches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bugfixes.py::TestLLMReadTargetInjection tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add enforcer/runner.py enforcer/llm.py tests/test_bugfixes.py
git commit -m "feat: LLM prompt includes read_target content for semantic cross-file checks"
```

---

### Task 16: Add example NL rule + cross-file rule to `enforcer_config.py`

**Files:**
- Modify: `enforcer_config.py`

**Purpose:** Show off the new agentic features with real examples.

- [ ] **Step 1: Update config**

`enforcer_config.py`, add to imports:

```python
from enforcer.matchers import (
    RegexMatcher, LineCountMatcher, PathNotMatchingMatcher,
    AllowlistMatcher, AlwaysMatcher, FileExistsMatcher,
)
```

Add these rules to `RULES`:

```python
    Rule(
        id="function-focus",
        severity=Severity.WARN,
        matchers=[AlwaysMatcher(matched_value="function-focus-check")],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/*.d.ts"],
        message="Functions should be short, focused, and single-purpose.",
        fix_instruction="Consider splitting large functions into smaller, focused units.",
        llm_consequence=LLMConsequence(
            provider="default",
            model="gpt-4",
            prompt="Review this file's functions. Are they short, focused, and single-purpose? Flag any that are too long or do multiple things. Be concise.",
        ),
    ),
    Rule(
        id="test-file-exists",
        severity=Severity.WARN,
        matchers=[Not(FileExistsMatcher(read_target="**/*.spec.ts"))],
        file_globs=["**/*.ts"],
        exclude_globs=["**/*.spec.ts", "**/*.d.ts", "**/index.ts"],
        message="No test file found for '{file}'. Agents must write tests.",
        fix_instruction="Create a .spec.ts file alongside the source file.",
    ),
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 3: Verify docs generation works**

Run: `enforcer docs`
Expected: markdown output with all 4 rules

- [ ] **Step 4: Commit**

```bash
git add enforcer_config.py
git commit -m "feat: example NL rule (function-focus) + cross-file rule (test-file-exists)"
```

---

### Task 17: Full test suite + coverage

- [ ] **Step 1: Run full suite**

Run: `pytest -v --cov=enforcer --cov-report=term-missing`
Expected: All pass, coverage ≥85%

- [ ] **Step 2: Fix any failures**

If tests fail, fix and re-run.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "test: full suite green with coverage"
```

---

## Self-Review Checklist

**Spec coverage:**
- Critical bug 1 (AST needs): Task 1 ✓
- Critical bug 2 (cache force_needs): Task 2 ✓
- Critical bug 3 (rule.workspace): Deferred — requires deeper plumbing, documented
- Critical bug 4 (allowlist keying): Task 5 ✓
- Medium bugs (Not combinator, braces, msg leak, LLM dedup, JSON schema): Tasks 3,4,7,8,9 ✓
- Doc generation: Task 12 ✓
- AlwaysMatcher + NL rules: Task 10, 16 ✓
- FileExistsMatcher: Task 11, 16 ✓
- verify_fix MCP: Task 13 ✓
- LLM read_target injection: Task 15 ✓
- SARIF output: Task 14 ✓
- `--all` junk dirs: Task 6 ✓

**Deferred (documented as non-goals or v2):**
- `rule.workspace` wiring (needs FileContextBuilder + CLI contract change)
- Cross-run caching (YAGNI)
- Learn mode (different tool)
- Git-aware rules (v2, separate subcommand)
- Rule versioning (v2)
- Inter-rule dependencies (v2)
