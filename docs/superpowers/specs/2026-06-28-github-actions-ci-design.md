# GitHub Actions CI Integration Design

**Date:** 2026-06-28
**Status:** Draft

## Goal

Enable the enforcer to run in GitHub Actions CI, scanning only ERROR severity without LLM calls. Support two scan modes: changed-files (fast feedback on pushes) and full-scan (thoroughness on PRs and master pushes). Usable cross-org with private repos via PAT auth.

## Context

- CLI already has `--severity`, `--no-llm`, `--format sarif`, `--output` flags
- `enforcer/reporter.py` already supports SARIF output
- `enforcer/rule.py:58-62` — `diff_only=True` returns `[]` when `changed_lines is None`
- `cli.py:27-48` — `_parse_diff_changed_lines` only handles `git diff --cached`
- No `.github/` directory exists yet
- `pyproject.toml` has tree-sitter dependencies (need installation in CI)
- 21 rules: 15 ERROR (always block) + 6 WARN (critical-component reminders)
- CI scans ERROR only — WARN is advisory in CI

## Problem

`diff_only=True` rules are dead code in CI: there is no git staging area in CI, so `changed_lines` is always `None`, so `diff_only` rules return `[]`. Need a way to compute `changed_lines` from a git ref (the CI merge base) instead of from `git diff --cached`.

## Section 1: CLI `--base-ref` Flag

### New `--output` Option on `check`

`check` command lacks `--output`. SARIF in CI needs file output. Add:

```python
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
```

In `check()`, after reporter render:
```python
if output:
    with open(output, "w", encoding="utf-8") as f:
        f.write(output_text)
else:
    click.echo(output_text)
```

### Mutual Exclusion

`--staged`, `--base-ref`, `--all` are mutually exclusive. Enforce at top of `check()`:

```python
exclusive = sum([bool(staged), bool(base_ref), bool(all_files)])
if exclusive > 1:
    click.echo("Error: --staged, --base-ref, and --all are mutually exclusive.", err=True)
    sys.exit(2)
```

### Generalize Diff Parsing

Current `_parse_diff_changed_lines(repo_root, file_path)` uses `git diff --cached`. Generalize to accept a ref:

```python
def _parse_diff_changed_lines(
    repo_root: str, file_path: str, ref: str | None = None
) -> set[int] | None:
    """Parse git diff -U0 for a file, return set of changed (added) line numbers.
    ref=None uses --cached (staged). ref set uses <ref>...HEAD."""
    diff_cmd = ["git", "diff", "-U0"]
    diff_cmd += ["--cached"] if ref is None else [f"{ref}...HEAD"]
    diff_cmd += ["--", file_path]
    ...
```

### `_collect_files` Gains base-ref Branch

```python
if base_ref:
    result = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        stderr=subprocess.DEVNULL, cwd=ws,
    )
    return result.decode().strip().split("\n") if result.strip() else []
```

### `_run_checks` Passes base_ref to Diff Parser

```python
def _run_checks(runner, builder, file_list, shared_ctx, ws, diff_ref=None):
    ...
    if diff_ref is not None or staged:  # staged uses ref=None (cached)
        ctx.changed_lines = _parse_diff_changed_lines(ws, f, ref=diff_ref)
```

`--base-ref` flows through the same `changed_lines` mechanism that `--staged` already uses, so `diff_only` rules work identically in CI.

~20 lines changed. No new files.

## Section 2: This Repo's Workflow

`.github/workflows/enforcer.yml` — two jobs, trigger-gated:

```yaml
name: enforcer

on:
  push:
    branches: [master, "feature/**", "fix/**", "refactor/**", "docs/**", "chore/**"]
  pull_request:
    branches: [master]

jobs:
  changed:
    name: changed-files
    if: github.event_name == 'push' && github.ref != 'refs/heads/master'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: build-wheel
        run: pip install build && python -m build --wheel
      - uses: ./.github/actions/enforcer
        with:
          install-method: wheel
          base-ref: origin/master

  full:
    name: full-scan
    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/master'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: build-wheel
        run: pip install build && python -m build --wheel
      - uses: ./.github/actions/enforcer
        with:
          install-method: wheel
          base-ref: ""
```

### Behavior

| Event | Job runs | Scope |
|-------|----------|-------|
| Push to feature/fix/refactor/docs/chore branch | `changed` | diff against `origin/master` |
| Push to master | `full` | entire repo (`--all`) |
| PR targeting master | `full` | entire repo (`--all`) |

- `fetch-depth: 0` on changed job — `git diff origin/master...HEAD` needs merge base
- Full scan doesn't need history (walks filesystem)
- `build-wheel` step runs before action — produces `dist/*.whl`
- Empty `base-ref` → action runs `--all`

## Section 3: Composite Action

`.github/actions/enforcer/action.yml`:

```yaml
name: enforcer
description: Run pre-commit-agent-enforcer convention checks

inputs:
  install-method:
    description: How to install enforcer. skip | pip | wheel
    default: pip
  base-ref:
    description: Git ref to diff against. Empty = full scan (--all)
    default: ""
  severity:
    description: Minimum severity to report
    default: error
  token:
    description: GitHub token for private repo checkout (cross-org)
    default: ${{ github.token }}

runs:
  using: composite
  steps:
    - name: setup-python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: install
      shell: bash
      run: |
        case "${{ inputs.install-method }}" in
          skip) echo "skip install" ;;
          wheel)
            pip install dist/*.whl ;;
          pip)
            pip install "git+https://x-access-token:${{ inputs.token }}@github.com/${{ github.repository }}.git@${{ github.sha }}" ;;
        esac

    - name: run-enforcer
      shell: bash
      run: |
        ARGS="--severity ${{ inputs.severity }} --no-llm --format sarif --output enforcer-results.sarif"
        if [ -n "${{ inputs.base-ref }}" ]; then
          ARGS="$ARGS --base-ref ${{ inputs.base-ref }}"
        else
          ARGS="$ARGS --all"
        fi
        python -m enforcer.cli check $ARGS
      continue-on-error: true

    - name: upload-sarif
      if: always()
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: enforcer-results.sarif

    - name: fail-on-violations
      if: steps.run-enforcer.outcome == 'failure'
      shell: bash
      run: exit 1
```

### Design Notes

- `continue-on-error: true` on run step — SARIF uploads even when violations exist
- Separate fail step preserves audit trail, then enforces exit code
- `install-method: wheel` — assumes `dist/*.whl` exists (build step in workflow)
- `install-method: pip` — installs from git via token, works cross-org with PAT
- `install-method: skip` — consumer already installed enforcer, action just runs it
- `token` defaults to `github.token` (same-repo). Cross-org consumer overrides with PAT secret
- `setup-python@v5` — ensures Python 3.11+ available, runner default may drift
- `--no-llm` hardcoded — CI never calls LLM
- `--severity error` default — CI only fails on ERROR; WARN is advisory in CI
- Empty `base-ref` → `--all` (full scan)

## Section 4: Cross-Org Consumption

External repo uses the action:

```yaml
- uses: org-name/pre-commit-agent-enforcer/.github/actions/enforcer@master
  with:
    install-method: pip
    token: ${{ secrets.ENFORCER_PAT }}
    base-ref: origin/master
```

- PAT needs `contents:read` on this repo (to clone via git+token)
- PAT stored as secret in consumer repo
- Repo stays private — PAT auth gates access

## Open Questions

1. **Tree-sitter**: `pip install` pulls tree-sitter language packs. `wheel` install bundles them. Confirm both paths work in CI.
2. **SARIF upload permissions**: `upload-sarif` action needs `security-events: write`. Document in README.

## Resolved

1. **Python setup**: `actions/setup-python@v5` with Python 3.11 added to composite action. `requires-python = ">=3.11"` in pyproject.toml.
