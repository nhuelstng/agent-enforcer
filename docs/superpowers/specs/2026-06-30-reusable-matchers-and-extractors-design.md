# Reusable Matchers and Extractors — Design

Date: 2026-06-30
Status: approved (design, post-review), pending implementation

## Goal

Make the cross-file key-set sync pattern reusable as built-in building blocks,
so consumers (notably `agent-skill-management-library`) stop copy-pasting
~80-line custom matchers into `enforcer_config.py`. Ship:

1. A `KeySetSyncMatcher` that generalizes "keys in this file must appear in
   the union of keys across N target files."
2. A dataclass-based extractor library (`EnvFileKeys`, `TerraformBlockKeys`,
   `JsonKeys`, `YamlKeys`, `IniSectionKeys`) covering common config formats.
3. A `StatusGate` combinator that replaces the hand-rolled
   `NewFilePairedFileMatcher` wrapper.
4. A fix to `_build_shared_ctx` so `read_targets` caches all glob matches by
   path (not just the first match per glob string).

## Motivation

The consumer `agent-skill-management-library/enforcer_config.py` ships two
hand-rolled matchers that should not need to exist:

- **`EnvTerraformSyncMatcher`** (~80 lines) — parses `KEY=VALUE` env-example
  files, parses named Terraform blocks by brace-counting, opens the TF files
  directly with `open()`, computes a set difference, emits matches. Two rules
  use it (env-config ↔ TF, env-secrets ↔ TF).
- **`NewFilePairedFileMatcher`** (~15 lines) — thin wrapper that gates an
  inner `PairedFileMatcher` on `file_ctx.status == "added"`.

Three problems follow:

1. **Not reusable.** The matcher opens files directly with `open()`,
   bypassing the `read_targets` / `shared_ctx` infrastructure that
   `AllowlistMatcher` uses. It cannot be unit-tested without real files on
   disk, and it duplicates context-building the runner already does.
2. **Domain logic in a generic tool.** The env/TF parsers are hand-rolled
   inline. Any future "env ↔ YAML config sync" or "tfvars ↔ backend vars
   sync" rule starts from scratch.
3. **The `read_targets` plumbing has a latent bug.** `_build_shared_ctx`
   (`enforcer/cli.py:156-170`) stores only the *first* glob match per target
   string (`shared_ctx.setdefault(target, ctx)` at `cli.py:169`). A glob
   like `infrastructure/aws/service/*/main.tf` matching two files loses the
   second. `EnvTerraformSyncMatcher` works around this by opening files
   itself — but that workaround is the reuse blocker.

## Scope

Three pieces, each landing in its existing-convention home:

- **`enforcer/matchers/keyset_sync.py`** — `KeySetSyncMatcher` (N read
  targets, exclusion set, set-diff). One file, one dataclass — matches the
  "one matcher per file" convention.
- **`enforcer/extractors/`** — new package. Dataclass extractors with an
  `extract(raw: str) -> set[str]` method. One extractor per file. Six
  extractors ship in v1: `EnvFileKeys`, `TerraformBlockKeys`, `JsonKeys`,
  `YamlKeys`, `IniSectionKeys`, plus the `Extractor` protocol in `core.py`.
- **`enforcer/combinators/core.py`** — `StatusGate` added alongside
  `AllOf`/`AnyOf`/`Not`/`NoneOf`/`OneOf`.
- **`enforcer/cli.py`** — `_build_shared_ctx` fixed to cache all glob
  matches by relative path.

Each piece lands where its contract says it belongs (matcher finds,
combinator composes matchers, extractor parses raw text). No new top-level
`building_blocks/` bucket — that would blur the clean
matcher/predicate/combinator/parser ontology.

## Non-goals

- **No domain-specific matcher.** `EnvTerraformSyncMatcher` is *not*
  shipped as a built-in. The enforcer is a generic convention tool, not an
  env-TF-specific one. Baking a domain matcher into core invites "please
  add my specific matcher" requests and blurs the boundary. The env↔TF rule
  becomes a ~5-line `KeySetSyncMatcher` wiring in the consumer's config,
  documented via `examples/env_terraform_sync.py`.
- **No nested-key selectors.** `JsonKeys`/`YamlKeys` extract top-level keys
  only. Nesting is YAGNI; most config-sync use cases are flat. A `# ponytail:`
  comment marks the ceiling and upgrade path (jsonpath/yq if needed).
- **No hard PyYAML dependency.** `YamlKeys` lazy-imports PyYAML and returns
  `set()` on missing module. Users who don't use the YAML extractor pay no
  dependency cost.
- **No refactor of `AllowlistMatcher`.** Its API is unchanged and it keeps
  working for single-target use (its existing fallback at
  `allowlist.py:22-25` glob-matches `shared_ctx` keys, which handles the
  path-keyed layout for single-file targets). The direct-key lookup at
  `allowlist.py:20` is now dead code (always returns `None`) but harmless.
  Multi-target union is `KeySetSyncMatcher`'s job, not `AllowlistMatcher`'s
  — the two matchers have different contracts (single-read-target vs.
  N-target union).

## Architecture

### Data flow

```
Rule(read_targets=["infrastructure/aws/service/*/main.tf"])
  ↓ _build_shared_ctx (FIXED: caches FileContext per matched path, not per glob string)
shared_ctx = {"infrastructure/aws/service/dev/main.tf": FileContext(...),
              "infrastructure/aws/service/prod/main.tf": FileContext(...),
              "__workspace__": ".", "__rules__": [...]}
  ↓ KeySetSyncMatcher.find(file_ctx, shared_ctx)
    - extract "used" keys from file_ctx via self.source_extractor
    - apply self.exclude_keys to "used"
    - for each target_glob: iterate shared_ctx keys matching glob, extract via self.target_extractor, union
    - emit Match per key in (used - allowed)
```

### File layout

```
enforcer/
  extractors/                ← NEW package
    __init__.py              ← exports Extractor, EnvFileKeys, TerraformBlockKeys,
                               JsonKeys, YamlKeys, IniSectionKeys
    core.py                  ← Extractor Protocol (structural, no ABC)
    env_file.py
    terraform_block.py
    json_keys.py
    yaml_keys.py
    ini_section_keys.py
  matchers/
    keyset_sync.py           ← NEW KeySetSyncMatcher
    __init__.py              ← + KeySetSyncMatcher export
  combinators/
    core.py                  ← + StatusGate
    __init__.py              ← + StatusGate export
  cli.py                     ← _build_shared_ctx fix
examples/
  env_terraform_sync.py     ← NEW: 5-line wiring of the env↔TF rule
tests/
  test_extractors/           ← NEW test package (one file per extractor)
  test_matchers/
    test_keyset_sync.py      ← NEW
  test_combinators/
    test_status_gate.py      ← NEW
  test_cli.py                ← extend: multi-match read_targets case
```

## Components

### 1. `KeySetSyncMatcher`

`enforcer/matchers/keyset_sync.py`:

```python
@dataclass
class KeySetSyncMatcher:
    """Cross-file key-set sync. Keys extracted from this file via source_extractor
    must appear (after exclude_keys removal) in the union of keys extracted from
    target files via target_extractor. Emits one Match per missing key.

    Target files are resolved from shared_ctx by glob-matching the keys populated
    by the runner's read_targets mechanism. No direct file I/O — fully testable
    via an injected shared_ctx dict.
    """
    source_extractor: "Extractor"
    target_extractor: "Extractor"
    target_globs: list[str]
    exclude_keys: set[str] = field(default_factory=set)
    needs: Needs = Needs.RAW

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        if not file_ctx.raw:
            return []
        used = self.source_extractor.extract(file_ctx.raw) - self.exclude_keys
        allowed: set[str] = set()
        for glob in self.target_globs:
            for path, ctx in self._matching_targets(glob, shared_ctx, file_ctx.path):
                if ctx.raw:
                    allowed |= self.target_extractor.extract(ctx.raw)
        return [
            Match(file=file_ctx.path, line=0, matched_value=key)
            for key in sorted(used - allowed)
        ]

    def _matching_targets(self, glob, shared_ctx, source_path):
        from enforcer.rule import _glob_match
        for key, ctx in shared_ctx.items():
            if key.startswith("__"):
                continue
            if key == source_path:
                continue  # source file must not satisfy its own target check
            if _glob_match(key, glob):
                yield key, ctx

    def __post_init__(self):
        if not self.target_globs:
            raise ValueError("target_globs must be non-empty — empty list emits a match for every source key")
```

Design rules:

1. **One source extractor, one target extractor** — not lists. The env↔TF
   case uses `EnvFileKeys` on the source and `TerraformBlockKeys` on the
   target. A future rule needing "keys must be in JSON *or* YAML file"
   composes with `AnyOf` of two `KeySetSyncMatcher` instances. Keeps the
   matcher simple.
2. **`exclude_keys` on the matcher, not the extractor.** Extractors are
   pure parsers; "this key is intentionally dev-local" is a rule-level
   decision.
3. **`target_globs` is a list** — supports the env↔TF case where both
   `dev/main.tf` and `prod/main.tf` must contain the key. Each glob
   contributes its matches; union across all.
4. **`_matching_targets` skips `__`-prefixed shared_ctx keys**
   (`__rules__`, `__workspace__`, `__change__`) — those are
   framework-internal, not file contexts.
5. **No file I/O in `find()`** — reads `ctx.raw` from `shared_ctx`. Tests
   inject a dict of `{path: FileContext(raw=...)}`. Standalone invocation
   (no runner) returns `[]` for missing targets — same defensive behavior as
   `AllowlistMatcher`.
6. **`line=0`** — same convention as `AllowlistMatcher`, `PairedFileMatcher`
   (violation is about the *set*, not a specific line).
7. **Self-matching guard** — `_matching_targets` skips `key == source_path`
   so a file that appears in both `file_globs` and `target_globs` can't
   satisfy its own target check (which would make the sync vacuously pass).
8. **`__post_init__` validation** — empty `target_globs` raises
   `ValueError`. Without this, an empty list means `allowed` stays empty
   and every source key emits a match (false-positive flood).
9. **Must live in `enforcer/matchers/keyset_sync.py`, not inline in
   `enforcer_config.py`.** Python 3.14's `@dataclass` decorator fails when
   a class is defined during `exec_module` without `sys.modules`
   registration (how `enforcer/config.py:44` loads `enforcer_config.py`).
   Defining `KeySetSyncMatcher` in a normally-imported module sidesteps
   this — the decorator runs at import time with proper `sys.modules`
   context. This is why the consumer's `EnvTerraformSyncMatcher` was a
   plain class (not `@dataclass`) — it was defined inline. The built-in
   matcher doesn't have that constraint.

### 2. Extractors package

`enforcer/extractors/core.py`:

```python
from __future__ import annotations
from typing import Protocol

class Extractor(Protocol):
    """Parses raw file text into a set of key strings. Pure function — no I/O."""
    def extract(self, raw: str) -> set[str]: ...
```

Protocol, not abstract base. Dataclass extractors satisfy it structurally —
no inheritance ceremony. `Extractor` is the type hint used by
`KeySetSyncMatcher.source_extractor` / `.target_extractor`.

`enforcer/extractors/env_file.py` — port of
`EnvTerraformSyncMatcher._extract_env_keys`:

```python
@dataclass
class EnvFileKeys:
    """Extracts KEY names from env-style 'KEY=VALUE' lines.
    Skips blank lines, comments (#), and lines without '='. Key is the
    substring before the first '=', stripped."""
    def extract(self, raw: str) -> set[str]:
        keys: set[str] = set()
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key = s.split("=", 1)[0].strip()
            if key:
                keys.add(key)
        return keys
```

`enforcer/extractors/terraform_block.py` — port of
`EnvTerraformSyncMatcher._extract_tf_block_keys`:

```python
@dataclass
class TerraformBlockKeys:
    """Extracts key names from a named Terraform block (e.g. 'app_environment = { ... }').
    Finds the block by name via regex, walks its body by brace-depth counting,
    extracts 'KEY =' or '"KEY" =' assignments. Block must be top-level
    (depth 1 within the block). Nested blocks are skipped."""
    block_name: str
    def extract(self, raw: str) -> set[str]:
        pattern = rf"\b{re.escape(self.block_name)}\s*=\s*\{{"
        m = re.search(pattern, raw)
        if not m:
            return set()
        depth = 0
        body_chars: list[str] = []
        for ch in raw[m.end() - 1:]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            if depth == 1:
                body_chars.append(ch)
        keys: set[str] = set()
        for line in "".join(body_chars).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            km = re.match(r'"?([A-Z][A-Z0-9_]*)"?\s*=', s)
            if km:
                keys.add(km.group(1))
        return keys
```

The brace-counting is fragile (doesn't handle HCL strings containing
`{`/`}`) but it's the existing behavior — porting it as-is avoids scope
creep. Marked with `# ponytail: brace-counting fails on HCL strings with
literal { }; hclparse if it bites`.

`enforcer/extractors/json_keys.py`:

```python
@dataclass
class JsonKeys:
    """Extracts top-level keys of a JSON object. Arrays and primitives return {}.
    Designed for flat config objects (package.json, tsconfig.json, .vscode/settings.json)."""
    # ponytail: top-level only; add jsonpath selector if nested sync needed
    def extract(self, raw: str) -> set[str]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
```

`enforcer/extractors/yaml_keys.py`:

```python
@dataclass
class YamlKeys:
    """Extracts top-level keys of a YAML mapping. Lists and scalars return {}.
    PyYAML imported lazily — users not using this extractor pay no dependency cost.
    Designed for flat config (docker-compose service env, GitHub Actions inputs/outputs)."""
    # ponytail: silent no-op if PyYAML absent; add hard dep if YAML sync becomes core use case
    def extract(self, raw: str) -> set[str]:
        try:
            import yaml  # lazy: avoid hard PyYAML dep for non-YAML users
        except ImportError:
            return set()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
```

`enforcer/extractors/ini_section_keys.py`:

```python
@dataclass
class IniSectionKeys:
    """Extracts keys within a named INI section. Useful for .editorconfig, .flake8,
    setup.cfg-style configs where keys must stay in sync across files."""
    section: str
    def extract(self, raw: str) -> set[str]:
        parser = configparser.ConfigParser()
        try:
            parser.read_string(raw)
        except configparser.Error:
            return set()
        if parser.has_section(self.section):
            return set(parser.options(self.section))
        return set()
```

`enforcer/extractors/__init__.py`:

```python
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys
from enforcer.extractors.json_keys import JsonKeys
from enforcer.extractors.yaml_keys import YamlKeys
from enforcer.extractors.ini_section_keys import IniSectionKeys

__all__ = [
    "Extractor", "EnvFileKeys", "TerraformBlockKeys",
    "JsonKeys", "YamlKeys", "IniSectionKeys",
]
```

Design rules for the package:

1. Each extractor is one file, one dataclass — matches the "one matcher per
   file" convention.
2. Extractors are stateless beyond construction params — no `find()`-mutated
   state.
3. `extract(raw: str) -> set[str]` is the only method. No `FileContext`
   dependency — keeps them composable and unit-testable with a string input.

### 3. `StatusGate` combinator

`enforcer/combinators/core.py` (added alongside existing combinators):

```python
@dataclass
class StatusGate:
    """Runs inner matcher only when file_ctx.status is in allowed_statuses.
    Returns [] otherwise. Composes any matcher — PairedFileMatcher, KeySetSyncMatcher,
    RegexMatcher, anything. Replaces hand-rolled NewFilePairedFileMatcher wrapper
    in agent-skill-management-library."""
    matcher: object
    allowed_statuses: set[str] = field(default_factory=lambda: {"added"})
    needs: Needs = Needs.RAW

    def find(self, file_ctx, shared_ctx=None) -> list[Match]:
        if file_ctx.status not in self.allowed_statuses:
            return []
        return _run(self.matcher, file_ctx, shared_ctx)
```

Design rules:

1. **Generalizes `NewFilePairedFileMatcher`** — that wrapper hard-codes
   `status == "added"`. `StatusGate` makes the status set configurable:
   `{"added"}`, `{"added", "modified"}`, `{"deleted"}`, any subset.
2. **`allowed_statuses` defaults to `{"added"}`** — the most common gate
   (new-file-only checks). Drop-in for the consumer's hand-rolled wrapper:
   `StatusGate(PairedFileMatcher(...))` replaces
   `NewFilePairedFileMatcher(PairedFileMatcher(...))`.
3. **Reuses `_run` helper** — same call path as `AllOf`/`AnyOf`. No new
   infra.
4. **`needs` delegates implicitly** — `StatusGate` declares `RAW` but the
   inner matcher's `needs` drives context building (the runner consults
   each matcher's `needs`). This matches the existing combinator pattern
   (`AllOf.needs = RAW`). Consequence: if the inner matcher needs
   `AST_PY` but `file_ctx.status` is not in `allowed_statuses`, the runner
   still builds the AST (wasted work, not a bug). `StatusGate.needs` is
   cosmetic; making it a `@property` delegating to the inner matcher would
   be more correct but breaks the combinator precedent, so it stays as-is.
5. **Not a predicate** — predicates filter `Match` objects *after* a
   matcher runs. `StatusGate` prevents the matcher from running at all.
   Different contract, lives in combinators.
6. **Finalizer-walk:** `_collect_finalizers` in `combinators/core.py:12`
   walks the tree for `finalize_duplicates`. `StatusGate` has a `.matcher`
   attribute (like `Not`), so the existing `elif hasattr(m, "matcher")`
   branch handles it — no change needed.

`StatusGate` added to `enforcer/combinators/__init__.py` `__all__`.

### 4. `shared_ctx` fix for multiple read targets

Current `_build_shared_ctx` (`enforcer/cli.py:156-170`):

```python
def _build_shared_ctx(config, builder, ws: str) -> dict:
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            if target in shared_ctx:          # BUG: skips if glob string already seen
                continue
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                target_ctx = builder.build(rel)
                shared_ctx.setdefault(target, target_ctx)  # BUG: only first match stored
    return shared_ctx
```

Two bugs:

1. `if target in shared_ctx: continue` — if two rules share a glob string,
   the second rule's matches are skipped entirely.
2. `shared_ctx.setdefault(target, target_ctx)` — stores under the *glob
   string* key, and only the first match. A glob like
   `infrastructure/aws/service/*/main.tf` matching `dev/main.tf` +
   `prod/main.tf` loses the second file.

Fixed:

```python
def _build_shared_ctx(config, builder, ws: str) -> dict:
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:        # dedupe by path, not by glob string
                    shared_ctx[rel] = builder.build(rel)
    return shared_ctx
```

Changes:

- Store `FileContext` under the *relative path* (e.g.
  `"infrastructure/aws/service/dev/main.tf"`), not the glob string.
  `KeySetSyncMatcher._matching_targets` then glob-matches `shared_ctx`
  keys against `target_globs`.
- Dedupe by path — if two rules declare the same target glob, or two globs
  overlap on a file, that file's context is built once.
- Drop the `if target in shared_ctx: continue` short-circuit — it was an
  optimization for the glob-string-keyed layout that no longer applies. The
  per-path dedupe handles the same intent correctly.

Backward compat:

- `AllowlistMatcher.read_target` is a single glob string. It currently does
  `shared_ctx.get(self.read_target)` — a direct key lookup on the glob
  string. After the fix, the key is the *path*, not the glob.
  `AllowlistMatcher` already has a fallback at `allowlist.py:22-25` that
  iterates `shared_ctx` keys via `_glob_match` — this fallback becomes the
  primary path with no code change. The fallback `break`s on the first
  matching key, so it handles single-file targets correctly. Multi-file
  union is `KeySetSyncMatcher`'s job, not `AllowlistMatcher`'s — the two
  matchers have different contracts (single-read-target vs. N-target
  union). `AllowlistMatcher`'s API is unchanged; the direct-key lookup at
  `allowlist.py:20` is now dead code (always returns `None`) but harmless.
- `FileExistsMatcher.read_target` — does `self.read_target in shared_ctx`
  (direct key lookup on the glob string). After the fix, the glob string is
  no longer a key, so this fast-path always misses. It falls through to the
  filesystem `root.glob()` fallback, which still works. This is a
  behavioral change: the cache fast-path is lost, filesystem glob runs on
  every call. Acceptable (the filesystem glob is cheap and `FileExistsMatcher`
  is rare), but the spec's original "no change" claim was wrong.
- `DocSyncMatcher` — reads `shared_ctx["__rules__"]` and
  `shared_ctx["__workspace__"]`, doesn't use `read_targets`. No change.

No migration burden — existing consumer configs with single-file
`read_targets` keep working because `_glob_match(path, glob)` matches a path
against its own glob.

## Example and consumer migration

`examples/env_terraform_sync.py`:

```python
"""Env-file ↔ Terraform block key sync. Replaces the 80-line
EnvTerraformSyncMatcher in agent-skill-management-library's enforcer_config.py."""
from enforcer import Rule, Severity
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys

TF_FILES = "infrastructure/aws/service/*/main.tf"

CONFIG_DEV_LOCAL_KEYS = {
    "ANTHROPIC_BASE_URL", "LLM_DEBUG_PROMPTS",
    "AUTO_APPROVE_DEFAULT_THRESHOLD", "AUTO_APPROVE_DEFAULT_COOLDOWN_MINUTES",
    "MCP_OAUTH_ENABLED", "DEV__AUTH__ADMIN_URL", "DEV__AUTH__ADMIN_REALM",
    "DEV__AUTH__ADMIN_USER", "DEV__AUTH__TARGET_REALM",
}

RULES = [
    Rule(
        id="env-config-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[TF_FILES],
            exclude_keys=CONFIG_DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.config.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.config.example but missing from app_environment in Terraform.",
        fix_instruction="Add the key to infrastructure/aws/service/{dev,prod}/main.tf app_environment, or add to exclude_keys if intentionally dev-local.",
    ),
    Rule(
        id="env-secrets-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_secrets"),
            target_globs=[TF_FILES],
            exclude_keys={"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEV__AUTH__ADMIN_PASSWORD"},
        )],
        file_globs=[".env.secrets.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.secrets.example but missing from app_secrets in Terraform.",
        fix_instruction="Add the key to infrastructure/aws/service/{dev,prod}/main.tf app_secrets, or add to exclude_keys if intentionally dev-local.",
    ),
]
```

Consumer migration (`agent-skill-management-library/enforcer_config.py`):

1. Delete `EnvTerraformSyncMatcher` class (~80 lines) and
   `NewFilePairedFileMatcher` wrapper.
2. Replace the two env↔TF rules with the `KeySetSyncMatcher` form above
   (5 lines each).
3. Replace `NewFilePairedFileMatcher(PairedFileMatcher(...))` with
   `StatusGate(PairedFileMatcher(...))`.
4. Add `read_targets=[TF_FILES]` to the two env↔TF rules (previously the
   matcher opened files directly).

Net diff in consumer: ~120 lines deleted, ~30 added. No behavior change —
the ported extractors produce identical key sets to the originals.

What stays in the consumer's config (domain knowledge, not generic):

- The specific glob paths (`infrastructure/aws/service/*/main.tf`).
- The `exclude_keys` sets (which keys are dev-local).
- The rule messages and fix instructions.
- The block names (`app_environment`, `app_secrets`).

This is correct — domain-specific knowledge lives in the consumer's config
where it belongs. The enforcer ships generic tools; the consumer expresses
its conventions using them.

## Testing strategy

Following AGENTS.md's paired-test convention:

```
tests/
  test_extractors/            ← NEW test package
    test_env_file.py
    test_terraform_block.py
    test_json_keys.py
    test_yaml_keys.py
    test_ini_section_keys.py
  test_matchers/
    test_keyset_sync.py       ← NEW
  test_combinators/
    test_status_gate.py       ← NEW
  test_cli.py                 ← extend: multi-match read_targets case
```

Extractor tests — pure string transforms, no fixtures:

- Happy path (valid input → expected key set)
- Empty string, malformed input → `set()`
- Comments/blanks skipped where relevant
- `TerraformBlockKeys`: missing block, nested blocks skipped, quoted/unquoted keys
- `YamlKeys`: missing PyYAML → `set()` (monkeypatch `import` to raise)
- `IniSectionKeys`: missing section → `set()`

`KeySetSyncMatcher` tests — inject `shared_ctx` dict, no disk I/O:

- Keys in source missing from targets → Match per missing key
- All keys present → `[]`
- `exclude_keys` removes from "used" side
- Multiple `target_globs` → union across all
- Multiple files per glob (the core new capability) → all contribute
- Empty `shared_ctx` (standalone invocation) → `[]`
- `__`-prefixed shared_ctx entries skipped
- Self-matching: source file appears in `target_globs` → source skipped in
  `_matching_targets` (no vacuous pass)
- Empty `target_globs` → `ValueError` on construction

`StatusGate` tests:

- `status="added"` + `allowed={"added"}` → inner matcher runs
- `status="modified"` + `allowed={"added"}` → `[]`, inner matcher never called
- Custom `allowed={"added", "modified"}`
- Composes with a matcher that has `finalize_duplicates` → finalizer still
  collected by `_collect_finalizers`

`_build_shared_ctx` test (extend `test_cli.py`):

- Glob matching 2+ files → all cached under relative paths
- Overlapping globs across rules → each file built once
- Existing single-file behavior still works

**Self-enforcement:** the existing `core-test-paired` rule in
`enforcer_config.py` uses `source_glob="enforcer/*.py"` (non-recursive), so
it does NOT cover `enforcer/extractors/*.py`. Add a new
`extractor-test-paired` rule to `enforcer_config.py`:

```python
Rule(
    id="extractor-test-paired",
    severity=Severity.ERROR,
    matchers=[PairedFileMatcher(
        source_glob="enforcer/extractors/*.py",
        derived_glob="tests/test_extractors/test_{stem}*.py",
        exclude_stems=["__init__", "core"],
    )],
    file_globs=["enforcer/extractors/*.py"],
    exclude_globs=["enforcer/extractors/__init__.py", "enforcer/extractors/core.py"],
    message="Extractor {file} has no paired test. Create tests/test_extractors/test_{stem}*.py",
    fix_instruction="Add a test file covering happy path, empty/malformed input, and format-specific edge cases.",
    rationale="Extractors are pure string transforms — trivial to test. Missing tests mean regressions in key extraction go unnoticed.",
),
```

`core.py` (the `Extractor` Protocol) is excluded — it's a type definition
with no behavior to test.

Not tested separately:

- `examples/env_terraform_sync.py` — it's documentation, not a code path.
  The pieces it uses are tested individually.
- `AllowlistMatcher` multi-target support — `AllowlistMatcher`'s contract is
  single-read-target; multi-target union is `KeySetSyncMatcher`'s job. The
  new `_build_shared_ctx` test covers multi-file caching; existing
  `AllowlistMatcher` tests cover its single-target use.

Run command: `pytest --tb=short -q` (per AGENTS.md).

## Decisions (locked)

| Decision | Choice | Reason |
|----------|--------|--------|
| Scope | C (both generalize pattern + building blocks) | Dissolves env-TF case AND opens door to other sync rules (YAML↔JSON, tfvars↔backend) |
| Extractor shape | B (dataclass with `.extract()` method) | Discoverable in `__all__`, parameterizable at construction, consistent with matcher/predicate dataclass convention. Trade-off: `AllowlistMatcher` already uses `Callable[[str], set[str]]` for the same role — the Protocol is more ceremony but earns its keep via parameterization (`TerraformBlockKeys(block_name=...)`) without `functools.partial` and via discoverability in `__all__` |
| Building-block location | C (split by existing role) | `StatusGate` → combinators, `KeySetSyncMatcher` → matchers, extractors → new package. Preserves clean ontology |
| Target resolution | C (fix `read_targets` to cache all matches by path) | Reuses existing infra, parse-once cache works, fully testable via injected `shared_ctx`. Fixes real latent bug |
| Migration | C (no alias, ship example) | Generic tool stays generic; domain knowledge lives in consumer config. Example documents the pattern |
| `AllowlistMatcher` scope | Unchanged (single-target contract) | Its existing `_glob_match` fallback handles path-keyed layout with no code change. Multi-target union is `KeySetSyncMatcher`'s job |
| PyYAML dependency | Lazy import in `YamlKeys` | No new hard dep for non-YAML users; silent no-op on missing module |
| Nested-key selectors | Top-level only (v1) | YAGNI; flat config covers common cases. `# ponytail:` marks upgrade path |

## Approaches considered

### Approach A: Promote `EnvTerraformSyncMatcher` as-is

Rejected. Locks in the `open()`-bypass anti-pattern, not reusable beyond
env/TF. Domain-specific matcher in a generic tool.

### Approach B: Generalize the pattern (chosen)

`KeySetSyncMatcher` + extractor library + `StatusGate`. Dissolves the
env-TF case and the whole class of "key-set sync" rules. Each piece lands
where its contract says (matcher → `matchers/`, combinator → `combinators/`,
extractors → new package). Runner gets a small fix so `read_targets` caches
all glob matches, not just the first.

### Approach C: Building-blocks bucket

Rejected. A `enforcer/building_blocks/` package would blur the clean
matcher/predicate/combinator/parser ontology. Each piece already has a
natural home.
