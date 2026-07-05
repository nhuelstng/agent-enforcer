# Dogfood Phase 1: Get to Green

**Date:** 2026-07-05
**Status:** Approved (Approach A: direct fix, no DI)
**Phase:** 1 of 3 (get to green → lock it down → dogfood harder)

## Goal

Make `enforcer check --all` pass clean on this repo. Resolve all 10
`arch-layer-deps` violations the enforcer flags on itself. Minimal diffs, no new
abstractions, no dependency injection, no test rewrite beyond what the fixes
demand.

This phase does **not** add new self-enforcement rules (Phase 2) or a CI gate
(Phase 3). It only makes the existing rules pass.

## Problem

Running `python -m enforcer.cli check --all --config enforcer_config.py` today
produces 10 `arch-layer-deps` ERRORs:

```
enforcer/matchers/allowlist.py:24    matchers -> rule
enforcer/matchers/doc_sync.py:30    matchers -> core
enforcer/matchers/doc_sync.py:34    matchers -> io
enforcer/matchers/keyset_sync.py:4  matchers -> extractors
enforcer/matchers/keyset_sync.py:57 matchers -> rule
enforcer/matchers/llm_check.py:6    matchers -> io
enforcer/matchers/paired_file.py:41 matchers -> rule
enforcer/rule.py:5                  rule -> types
enforcer/rule.py:6                  rule -> combinators
enforcer/runner.py:6                core -> io
```

(Exact line numbers may drift; the set of violations is stable.)

Root causes:
1. `_glob_match` is re-exported by `rule.py` (mid-layer) and imported *up* by
   matchers and `context.py` via lazy `from enforcer.rule import _glob_match`
   inside function bodies. The import graph walker sees through lazy imports
   (it walks the AST, not just top-level statements), so the dodge doesn't
   work — the violations fire anyway.
2. `llm_check.py` imports `call_llm` + `escape_content` from `enforcer.llm`
   (classified `io`). `runner.py` imports `LLMExecutor` from the same module.
3. `doc_sync.py` lazy-imports `load_config` (core) and `render_rules_doc`
   (io) as a standalone fallback when `shared_ctx["__rules__"]` is absent.
4. `rule.py` imports `AllOf` from `combinators.core`; `("rule", "combinators")`
   is missing from `allowed_edges`.
5. `rule.py` imports from `enforcer.types`; the `rule -> types` edge is also
   missing from `allowed_edges` (rule.py:5 violation above).

Additionally, `scratch_violations.py` is committed debug cruft at the repo
root that triggers `no-print` and `class-capwords` — it should not be in the
repo.

## Design

### Section 1: Glob imports — direct to `glob_util`

`glob_match` lives in `enforcer/glob_util.py`, which is **unclassified** (not
in any layer glob in the architecture rule). Importing from an unclassified
module is never an `arch-layer-deps` violation — the matcher's
`_layer_for_path` returns `None` and the import is skipped.

`rule.py` re-exports `glob_match` as `_glob_match` for historical reasons.
Matchers and `context.py` import the alias from `rule.py` (mid-layer), which
trips the rule. Fix: every consumer imports `glob_match` directly from
`enforcer.glob_util`. The lazy imports inside function bodies are removed
entirely.

| File | Change |
|------|--------|
| `enforcer/matchers/paired_file.py` | Remove lazy `from enforcer.rule import _glob_match` at line 41; add top-level `from enforcer.glob_util import glob_match`; rename call site `_glob_match` → `glob_match`. |
| `enforcer/matchers/allowlist.py` | Same, two call sites (lines 24 and 41). |
| `enforcer/matchers/keyset_sync.py` | Same, one call site (line 57). |
| `enforcer/context.py` | Same, one call site (line 79). |
| `enforcer/runner.py` | `from enforcer.rule import Rule, _glob_match` → split into `from enforcer.rule import Rule` + `from enforcer.glob_util import glob_match as _glob_match`. Keeps all call sites unchanged. |
| `tests/test_glob_doublestar.py` | `from enforcer.rule import _glob_match` → `from enforcer.glob_util import glob_match as _glob_match`. Zero call-site changes. |

`rule.py` keeps `from enforcer.glob_util import glob_match as _glob_match` for
its own `_excluded()` method — no violation since `glob_util` is unclassified.

### Section 2: Reclassify `llm.py` out of `io`

`enforcer/llm.py` is currently in the `io` layer:

```python
"io": ["enforcer/cli.py", "enforcer/mcp_server.py",
        "enforcer/reporter.py", "enforcer/docs.py",
        "enforcer/explain.py", "enforcer/fix.py",
        "enforcer/ignore.py", "enforcer/llm.py"],
```

But `llm.py` is shared infrastructure, not user-facing I/O. It defines:
- `call_llm` — httpx call to an LLM provider (no stdin/stdout/filesystem).
- `LLMExecutor` — orchestrates `call_llm` for consequence execution.
- `escape_content`, `_strip_think_tags` — pure string transforms.
- `get_provider_config`, `DEFAULT_PROVIDERS` — config resolution.

It's imported by both `runner.py` (core) and `llm_check.py` (matchers).
Classifying it as `io` makes both imports violations. Reclassifying it as
**unclassified** (like `glob_util`, `import_graph`) resolves both:

| File | Change |
|------|--------|
| `enforcer_config.py` | Remove `"enforcer/llm.py"` from the `io` layer globs. No new layer added — unclassified is simpler and matches `glob_util` precedent. |

Resolves:
- `llm_check.py → llm.py` (matchers→io was violation; now `llm` is unclassified).
- `runner.py → llm.py` (core→io was violation; now `llm` is unclassified).

**Cost:** `llm.py` is no longer gated by the architecture rule. Acceptable —
it's infrastructure, like `glob_util` and `import_graph`, which are also
unclassified. Phase 2 may add a rule that unclassified modules must not import
from `io` (catches drift), but that's out of scope here.

### Section 3: Remove `DocSyncMatcher` standalone fallback

`DocSyncMatcher.find()` lazy-imports `load_config` (core) and
`render_rules_doc` (io) as a fallback when `shared_ctx["__rules__"]` is
absent:

```python
rules = shared_ctx.get("__rules__")
workspace = shared_ctx.get("__workspace__", ".")
if rules is None:
    from enforcer.config import load_config
    config = load_config(self.config_path)
    rules = config.rules
    workspace = config.workspace or "."
from enforcer.docs import render_rules_doc
fresh = render_rules_doc(rules, workspace=workspace)
```

The runner always populates `shared_ctx["__rules__"]` (see `check_runner.py`
`build_shared_ctx`: `shared_ctx["__rules__"] = config.rules`). The fallback
exists only for standalone matcher invocation without a runner — which no
production caller does. The lazy imports trip `matchers→core` and
`matchers→io`.

Fix: move the `render_rules_doc` call out of the matcher entirely. The runner
pre-renders the doc and stashes the string in `shared_ctx["__rendered_doc__"]`.
`DocSyncMatcher` becomes pure: read on-disk `doc_path`, compare to
`shared_ctx["__rendered_doc__"]`. No imports from `io` or `core`. The
`config_path` field is removed — it only existed to feed the fallback.

`render_rules_doc` is a pure function (rules → markdown string) that lives in
`docs.py` (io) for packaging reasons, not because it does I/O. Moving it to a
lower layer would be a bigger refactor; pre-rendering in the runner is the
minimal A-compliant fix.

| File | Change |
|------|--------|
| `enforcer/matchers/doc_sync.py` | Remove `config_path` field. Remove lazy imports of `load_config` and `render_rules_doc`. Read rendered doc from `shared_ctx["__rendered_doc__"]` (string). Compare to on-disk `doc_path`. Update docstring. |
| `enforcer/check_runner.py` | In `build_shared_ctx`, after setting `__rules__`, call `render_rules_doc(config.rules, workspace=config.workspace or ws)` and set `shared_ctx["__rendered_doc__"]`. Import `render_rules_doc` from `enforcer.docs` here (check_runner already imports `enforcer.import_graph`). |
| `enforcer_config.py` | `DocSyncMatcher(config_path="enforcer_config.py", doc_path="CONVENTIONS.md")` → `DocSyncMatcher(doc_path="CONVENTIONS.md")`. |

Test impact:
- `tests/test_matchers/test_doc_sync.py` — all 5 tests construct
  `DocSyncMatcher(config_path=..., doc_path=...)` and most pass
  `{"__rules__": ...}` or `{"__rules__": None}`. Update to:
  - Remove `config_path=` from constructions.
  - Replace `{"__rules__": ...}` with `{"__rendered_doc__": <rendered string>}`.
  - `test_doc_sync_in_sync`: already renders via `render_rules_doc` — pass that
    string as `__rendered_doc__`.
  - `test_doc_sync_stale`: pass `{"__rendered_doc__": "fresh render"}`, write
    stale content to disk.
  - `test_doc_sync_missing_file`: pass `{"__rendered_doc__": "fresh render"}`,
    no file on disk.
  - `test_doc_sync_uses_shared_ctx_rules`: rename intent — now tests that
    `__rendered_doc__` is used. Same shape.
  - `test_doc_sync_load_config_error_propagates`: **remove**. The fallback is
    gone; this test exercises removed behavior.

### Section 4: Add missing `allowed_edges`

`rule.py` imports from `types` and `combinators`. Both are below `rule` in the
layer model (rule composes combinators; both depend on types). Add the edges:

| File | Change |
|------|--------|
| `enforcer_config.py` | Add `("rule", "types")` and `("rule", "combinators")` to `allowed_edges`. |

Resolves:
- `rule.py → types` (rule→types was violation).
- `rule.py → combinators` (rule→combinators was violation).

### Section 5: Delete repo cruft

| File | Change |
|------|--------|
| `scratch_violations.py` | Delete. Debug scratch file at repo root, triggers `no-print` and `class-capwords`. Not referenced anywhere. |

## Verification

After all changes:

```bash
python -m enforcer.cli check --all --config enforcer_config.py
# Expected: No issues found.

pytest --tb=short -q
# Expected: all pass, minus 1 removed test (test_doc_sync_load_config_error_propagates).
```

## Change summary

| Category | Files touched | Test churn |
|----------|--------------|------------|
| Glob imports (Section 1) | 6 source + 1 test | 1 test file updated (import path only) |
| `llm.py` reclassify (Section 2) | 1 config line | 0 |
| `DocSyncMatcher` fallback removal (Section 3) | 1 matcher + 1 runner + 1 config + 1 test | 1 test removed, 4 updated |
| Missing edges (Section 4) | 1 config line | 0 |
| Scratch file deletion (Section 5) | 1 file deleted | 0 |

**Total: ~10 files, 1 test removed, ~5 tests updated. Zero new abstractions.
Zero dependency injection.**

## Out of scope (Phase 2 / 3)

- New self-rules: ban function-body lazy imports, enforce `_glob_match` import
  source, config-size cap, scratch-file ban. (Phase 2)
- CI gate: `enforcer check --all` must pass on PRs. (Phase 3)
- Split `enforcer_config.py` under 400 lines, remove its `file-max-lines`
  self-exemption. (Phase 3)
