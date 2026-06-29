# LLM Matcher + Change Context — Design

Date: 2026-06-29
Status: approved (design), pending implementation

## Goal

Three coupled features, one scope:

1. **LLM-as-check.** Today LLMs are a *consequence* that fires after a deterministic rule fails (attaches analysis text to existing matches). We want LLM as the check itself — the matcher calls the LLM and emits matches.
2. **Change-aware input.** Rules need to reason about the whole change (modified files + commit message), not one file at a time. Example: "does the commit message align with the modified files?"
3. **Creation/deletion events.** Matchers must distinguish added vs modified vs deleted vs renamed files and react to folder creation/deletion.

These three are one design because they share plumbing: a `ChangeContext` struct that carries the change metadata, and a `FileContext.status` field that carries the per-file event kind.

## Non-goals

- Full audit-grade LLM checks. LLM matchers are sanity checks; fast models, fail-open on LLM errors.
- Dir-level git tree diff (exact folder creation/deletion detection). Folder lists are derived from file statuses; approximate is fine. Upgrade path noted in code.
- Fail-closed LLM behavior. Out of scope; fail-open default, override later if a rule needs it.
- Changing existing matchers' behavior around deletion events. Noted as follow-up; each matcher's event handling is its own decision.

## Design

### 1. LLMMatcher (new matcher)

File: `enforcer/matchers/llm_check.py`
Test: `tests/test_matchers/test_llm_check.py`

```python
@dataclass
class LLMMatcher:
    prompt: str
    provider: str = "custom"
    model: str = "zai-org/GLM-5.1-FP8"   # config author overrides for faster
    timeout: int = 30
    needs: Needs = Needs.RAW
```

#### find() flow

1. If `shared_ctx.get("__llm_enabled__") is False` → return `[]`. Honors `--no-llm` flag.
2. Build prompt: matcher's JSON-output instruction preamble (below) + user's `prompt` field.
   - **CONTENT phase** (per-file, `file_ctx.raw` is real file content): include fenced `file_ctx.raw` (reuse `LLMExecutor._build_prompt`'s escaping). Include `ChangeContext` summary if `shared_ctx["__change__"]` present.
   - **METADATA phase** (`run_metadata_rules` passes a fake ctx with `raw="__enforcer_sentinel__"`): ignore `file_ctx.raw`. Build prompt body from `shared_ctx["__change__"]` only — commit message + file lists (created/modified/deleted). If `__change__` is absent, return `[]` (nothing to check).
3. Call LLM via module function `call_llm(provider, model, prompt, timeout)` (extracted from `LLMExecutor`, see §4).
4. Parse response:
   - Try `json.loads(response)`.
   - `{"pass": true}` → return `[]`.
   - `{"violations": [{"file": <path>, "line": <int>, "reason": <text>}, ...]}` → emit one `Match` per violation: `Match(file=<path or file_ctx.path>, line=<line or 0>, matched_value=<reason>, message=<reason>)`.
   - JSON parse fails → fall back to PASS/FAIL text scan. If response (case-insensitive) starts with `PASS` → `[]`. Else one `Match(file=file_ctx.path, line=0, matched_value=<full response>, message=<full response>)`.
   - Note: for METADATA-phase matches, `file_ctx.path` is the workspace sentinel path. LLM should always specify `file` in METADATA-phase violations; if it doesn't, the match lands on the workspace path (line 0). Acceptable — message carries the real signal.
5. LLM call errors (timeout, network, non-2xx) → return `[]` **fail-open**. Sanity checks must not block commits on LLM outage. Write one line to stderr: `[enforcer] LLM matcher <id> failed: <error>` (matcher does not know its rule id; message uses object id() as fallback — acceptable for logs).

#### Prompt preamble (matcher injects before user's prompt)

```
You are a convention checker. Output JSON only, no prose.
{"pass": true}  if checks pass
{"violations": [{"file": "<relative path>", "line": <int>, "reason": "<text>"}]}  if not
```

#### Composition

LLMMatcher is a matcher like any other. Composes via `AllOf`/`AnyOf`/`Not`/`NoneOf`/`OneOf`. `_collect_needs` and `_collect_finalizers` work unchanged (no `finalize_duplicates` method).

#### Phases

- **CONTENT phase** (per-file): one LLM call per file. Slow for large changes; config author's responsibility.
- **METADATA phase** (once per run): `find()` reads `shared_ctx["__change__"]` to get commit_msg + file lists, builds prompt body from the change summary (not from `file_ctx.raw`, which is the sentinel). Emits matches across multiple files — LLM should specify `file` in each violation. One LLM call total. Use this for whole-change questions like the example rule.

No `finalize_duplicates()` — LLM returns all violations in one call. Two-phase not needed.

### 2. ChangeContext (new type)

File: `enforcer/types.py`

```python
@dataclass
class ChangeContext:
    """Carries the change metadata: commit message, branch, and file event lists.
    Stored in shared_ctx["__change__"]. METADATA-phase and finalizer matchers read it."""
    commit_msg: str = ""
    branch: str = ""
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)  # new paths

    @property
    def created_dirs(self) -> set[str]:
        # ponytail: approximate — dir listed if any child file created. Exact dir-level needs git tree diff, add when needed.
        return {str(Path(f).parent) for f in self.created if f}

    @property
    def deleted_dirs(self) -> set[str]:
        # ponytail: approximate — dir listed if any child file deleted. Exact dir-level needs git tree diff, add when needed.
        return {str(Path(f).parent) for f in self.deleted if f}
```

### 3. FileContext.status (new field)

File: `enforcer/types.py`

Add field to `FileContext`:

```python
status: str = "modified"  # "added" | "modified" | "deleted" | "renamed"
```

Existing matchers ignore it (they don't read `status`). Per-file matchers that care about events check it. Default `"modified"` keeps existing behavior when status info unavailable (all_files/paths mode).

### 4. Plumbing

#### 4a. Extract LLM call functions from LLMExecutor

File: `enforcer/llm.py`

Extract `_get_provider_config` and `_call_llm` as module-level functions:

```python
def get_provider_config(provider: str) -> dict: ...
def call_llm(provider: str, model: str, prompt: str, timeout: int) -> str: ...
```

`LLMExecutor` keeps thin wrappers calling the module functions — backwards compatible, existing tests pass unchanged. `LLMMatcher` calls module functions directly.

#### 4b. git diff --name-status parsing

File: `enforcer/cli.py`

In `_collect_files` (staged and base_ref modes): run `git diff --name-status` instead of `--name-only`. Parse first column letter:

- `A` → `added`
- `M` → `modified`
- `D` → `deleted`
- `R` → `renamed` (use new path, the second column)
- `C` → treat as `added` (copy)

Return `(file_list, status_map)` where `status_map: dict[str, str]`. For `all_files`/`paths` modes: empty `status_map` (defaults to `"modified"` via `FileContext.status` default).

#### 4c. Populate FileContext.status

File: `enforcer/cli.py` in `_run_checks`

```python
status = status_map.get(f, "modified")
ctx = dataclasses.replace(ctx, status=status,
                          changed_lines=_parse_diff_changed_lines(...))
```

#### 4d. Build ChangeContext once

File: `enforcer/cli.py` in `check` command, after `_build_shared_ctx`:

```python
change_ctx = _build_change_context(ws, status_map, staged, base_ref)
shared_ctx["__change__"] = change_ctx
```

`_build_change_context` helper reads:
- `commit_msg` from `.git/COMMIT_EDITMSG` (reuse logic from `CommitMessageMatcher` — read first non-merge line).
- `branch` from `git rev-parse --abbrev-ref HEAD`.
- `created`/`modified`/`deleted`/`renamed` lists from `status_map`.

#### 4e. Set __llm_enabled__ flag

File: `enforcer/runner.py`

In `run()` and `run_metadata_rules()`: set `shared_ctx["__llm_enabled__"] = self.llm_executor.enabled` at the start. One line each.

### 5. Example rule — commit message aligns with changes

Added to `enforcer_config.py`:

```python
Rule(
    id="commit-msg-aligns-with-changes",
    severity=Severity.WARN,  # sanity check, not hard gate
    matchers=[LLMMatcher(
        prompt="Given the commit message and the modified file list, does the message accurately describe these changes? Lenient — sanity check only, not a full audit.",
        model="zai-org/GLM-5.1-FP8",
        timeout=30,
    )],
    file_globs=["*"],
    rule_type=RuleType.METADATA,
    message="Commit message may not align with changes. LLM: {matched_value}",
    fix_instruction="Rewrite commit message to describe the actual changes.",
),
```

The matcher's `find()` (METADATA phase) reads `shared_ctx["__change__"]` to get commit_msg + file lists, builds the prompt, calls the LLM, parses JSON violations.

### 6. Creation/deletion integration

No new matcher classes for event handling. `FileContext.status` + `ChangeContext` lists enable event-awareness. Existing matchers become event-aware by checking `status` when relevant.

- `PairedFileMatcher`: behavior around deleted sources is a separate decision. Noted as follow-up; this spec does not change its behavior.
- `FileExistsMatcher` + `Not` already covers "created folder needs X" patterns.
- `ChangeContext.created_dirs`/`deleted_dirs` enable folder-level checks in METADATA-phase rules.
- New event-specific matchers added per-need in future specs.

### 7. Testing

| Test file | Covers |
|---|---|
| `tests/test_matchers/test_llm_check.py` | PASS→no match, FAIL JSON→structured matches, JSON parse fail→text fallback, LLM error→fail-open (no match), `__llm_enabled__=False`→no call, missing file/line defaults to file_ctx.path/0 |
| `tests/test_change_context.py` | created_dirs/deleted_dirs derivation, status letter parsing (A/M/D/R), empty ChangeContext defaults |
| `tests/test_metadata_rules.py` (extend) | commit-msg-alignment rule with mocked LLM, reads `__change__` |
| `tests/test_file_context_status.py` | default value, `dataclasses.replace` populates it, existing matchers unaffected |
| `tests/test_llm.py` (extend) | extracted module functions `call_llm`/`get_provider_config` work standalone; `LLMExecutor` wrappers still work (backwards compat) |

### 8. Scope notes

- LLMMatcher in CONTENT phase = one LLM call per file. Slow on large changes. Documented; config author's choice. METADATA phase recommended for whole-change questions.
- Fail-open on LLM errors. Override later if a rule needs fail-closed.
- Folder-level events are approximate (derived from file statuses). Exact dir-level detection via git tree diff is a future enhancement; upgrade path noted in `ChangeContext` ponytail comments.
- `PairedFileMatcher` deletion behavior unchanged in this spec. Future spec decides: should deleting a source file exempt it from the paired-test requirement?

### 9. Files touched

| File | Change |
|---|---|
| `enforcer/types.py` | Add `ChangeContext` dataclass; add `status` field to `FileContext` |
| `enforcer/matchers/llm_check.py` | New: `LLMMatcher` |
| `enforcer/matchers/__init__.py` | Export `LLMMatcher` |
| `enforcer/llm.py` | Extract `call_llm` + `get_provider_config` as module functions; `LLMExecutor` wraps them |
| `enforcer/cli.py` | `_collect_files` returns status_map; `_run_checks` sets `FileContext.status`; new `_build_change_context` helper; inject `shared_ctx["__change__"]` |
| `enforcer/runner.py` | Set `shared_ctx["__llm_enabled__"]` in `run()` + `run_metadata_rules()` |
| `enforcer_config.py` | Add `commit-msg-aligns-with-changes` example rule |
| `tests/test_matchers/test_llm_check.py` | New: LLMMatcher tests |
| `tests/test_change_context.py` | New: ChangeContext tests |
| `tests/test_file_context_status.py` | New: FileContext.status tests |
| `tests/test_metadata_rules.py` | Extend: commit-msg-alignment rule |
| `tests/test_llm.py` | Extend: extracted module functions backwards compat |
