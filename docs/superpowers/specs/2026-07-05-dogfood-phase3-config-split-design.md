# Dogfood Phase 3: Config Split + Reviewer Fixes — Design

**Date:** 2026-07-05
**Status:** Approved (Approach A: config split via rule composition)
**Phase:** 3 of 3 (get to green → lock it down → dogfood harder)

## Goal

Split the monolithic 866-line `enforcer_config.py` into a focused package
of small sub-config files, each under 200 lines. Remove the
`file-max-lines` exemption and the `config-size-cap` WARN rule — both
obsolete after the split. Fix the Phase 2 reviewer finding on
`CanonicalImportMatcher` multi-name import UX.

## Problem

1. **Config bloat:** `enforcer_config.py` is 866 lines, exempted from
   `file-max-lines` (400). The Phase 2 `config-size-cap` WARN rule (900) is
   a temporary guard. The file is hard to navigate — rule sections are
   delimited by comments but not by file boundaries.

2. **Reviewer finding (Phase 2, medium):** `CanonicalImportMatcher` emits
   one `Match` per import statement when ANY name is non-canonical. The
   `matched_value` is the full import line, so when a line imports 5 names
   and only 1 is non-canonical, the developer must guess which symbol
   triggered the violation.

3. **Exemptions:** 3 rules exempt `enforcer_config.py` from checks
   (`file-max-lines`, `constants-upper-case`, `no-magic-numbers`). After the
   split, each sub-config file should pass these rules without exemptions.

## Design

### Section 1: Config split — package structure

Replace `enforcer_config.py` (single file) with `enforcer_config/` (package).
`load_config()` in `config.py` must be updated: current implementation uses
`importlib.util.spec_from_file_location("enforcer_config", config_path)` which
only works for file paths (`.py`), not package directories. After the split,
`config_path` is `"enforcer_config"` (a package name). Fix: if `config_path`
ends in `.py`, use `spec_from_file_location` (backward compat for file-based
configs); otherwise use `importlib.import_module(config_path)` (package support).
CLI and MCP server defaults: `"enforcer_config.py"` → `"enforcer_config"`.

```
enforcer_config/
  __init__.py          — composition + WORKSPACE + SEVERITY_ACTIONS + LLM_CONFIG
  git_rules.py         — branch naming, commit message format
  test_rules.py        — test pairing (5), test coverage (4), docstring conventions (4)
  arch_rules.py        — layer deps, private imports, canonical imports, layer direction (5), config hygiene (2)
  style_rules.py       — nesting depth, interface, file length, function complexity (3), wildcard imports, TODO owner, docstrings
  hygiene_rules.py     — __all__ sorted, no side effects, constants, magic numbers, naming, no print, no bare except, no secrets, no debug, no type:ignore, no scratch files
  self_enforce.py      — reminders (6), CONVENTIONS.md sync, README LLM, commit-msg LLM, facade rules (2)
```

Each sub-config:
- Imports what it needs from `enforcer` and `enforcer.matchers`.
- Defines a `*_RULES` list (e.g., `GIT_RULES = [Rule(...), Rule(...)]`).
- No `WORKSPACE`, `SEVERITY_ACTIONS`, or `LLM_CONFIG` — those live in
  `__init__.py` only.

`__init__.py` composes:
```python
from enforcer_config.git_rules import GIT_RULES
from enforcer_config.test_rules import TEST_RULES
from enforcer_config.arch_rules import ARCH_RULES
from enforcer_config.style_rules import STYLE_RULES
from enforcer_config.hygiene_rules import HYGIENE_RULES
from enforcer_config.self_enforce import SELF_ENFORCE_RULES

RULES = [
    *GIT_RULES,
    *TEST_RULES,
    *ARCH_RULES,
    *STYLE_RULES,
    *HYGIENE_RULES,
    *SELF_ENFORCE_RULES,
]
```

### Section 2: Rule updates after split

**Remove `config-size-cap` rule** — obsolete after split. Each file is under
200 lines; the `file-max-lines` rule (400) covers individual files.

**Remove `enforcer_config.py` exemptions:**

| Rule | Current exemption | After split |
|------|-------------------|-------------|
| `file-max-lines` | `exclude_globs=["enforcer/cli.py", "enforcer_config.py"]` | Remove `"enforcer_config.py"` — each sub-config is under 400 |
| `constants-upper-case` | `exclude_globs=[..., "enforcer_config.py"]` | Remove `"enforcer_config.py"` — sub-configs should follow the rule |
| `no-magic-numbers` | `exclude_globs=[..., "enforcer_config.py"]` | Remove `"enforcer_config.py"` — sub-configs should follow the rule |

**Update path references:**

| Rule | Current `file_globs` | After split |
|------|---------------------|-------------|
| `no-duplicate-rule-ids` | `["enforcer_config.py"]` | `["enforcer_config/__init__.py"]` |

**Note on `constants-upper-case` and `no-magic-numbers`:** The config files
use `max_lines=400`, `max_value=75`, etc. — these are integers passed as
constructor arguments, not bare literals. The matchers check for bare magic
numbers in expressions, not keyword args. The exemptions were likely
precautionary. After the split, remove the exemptions and verify the rules
pass. If they don't, the sub-configs need to extract constants — but this is
unlikely given the matcher's design.

**Fallback:** If removing the `constants-upper-case` or `no-magic-numbers`
exemptions causes violations, keep the exemption but update the path to
`enforcer_config/*.py` (glob the package directory) rather than the old
single-file path. The goal is no blanket exemptions for the config package
— if a specific file needs one, it gets a targeted exemption.

### Section 3: Fix `CanonicalImportMatcher` multi-name import UX

**Problem:** When `from enforcer.rule import Rule, _glob_match` is flagged,
the `matched_value` is the full import text. The developer must search the
canonical map to find which symbol triggered the violation.

**Fix:** Emit one `Match` per non-canonical symbol. Set `matched_value` to a
descriptive string: `f"{name} (from {module}, should be from {canonical_module})"`.

In `enforcer/matchers/canonical_import.py`:
- Rename `_has_non_canonical` → `_non_canonical_names`, return `list[str]`
  (the non-canonical names) instead of `bool`.
- `find()` emits one `Match` per non-canonical name.
- `matched_value` = `f"{name} (from {module}, should be from {canonical[name]})"`.

**Test updates:** `tests/test_matchers/test_canonical_import.py` — update
the multi-name positive tests to assert `len(matches) == 1` (one per
non-canonical name, not one per statement). The single-name tests stay the
same.

### Section 4: Post-split cleanup

- Delete `enforcer_config.py` (replaced by `enforcer_config/` package).
- Regenerate `CONVENTIONS.md`.
- Verify `enforcer check --all` passes and all tests pass.

### Section 5: CI (no changes needed)

The existing `enforcer.yml` workflow already:
- Runs `enforcer check --all` on PRs (the `full-scan` job).
- Blocks on ERROR violations (the `fail-on-violations` step exits 1).
- Uses `--severity error` (warnings don't block — intentional).

No CI changes needed. The gate auto-picks-up the new config path.

## Verification

After all changes:

```bash
python -m enforcer.cli check --all --config enforcer_config
# Expected: No issues found.

pytest --tb=short -q
# Expected: all pass

wc -l enforcer_config/*.py
# Expected: each file under 200 lines
```

## Change summary

| # | Item | Files |
|---|------|-------|
| 1 | Create `enforcer_config/` package (7 files) | `enforcer_config/__init__.py`, `git_rules.py`, `test_rules.py`, `arch_rules.py`, `style_rules.py`, `hygiene_rules.py`, `self_enforce.py` |
| 2 | Delete `enforcer_config.py` | 1 file deleted |
| 3 | Remove `config-size-cap` rule | (in `style_rules.py`) |
| 4 | Remove `enforcer_config.py` exemptions | (in `style_rules.py`, `hygiene_rules.py`) |
| 5 | Fix `CanonicalImportMatcher` multi-name UX | `enforcer/matchers/canonical_import.py` + `tests/test_matchers/test_canonical_import.py` |
| 6 | Regenerate `CONVENTIONS.md` | `CONVENTIONS.md` |

**Total: 7 new files, 2 deleted, 2 modified. Zero new abstractions.**
