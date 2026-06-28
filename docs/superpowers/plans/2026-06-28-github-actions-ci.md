# GitHub Actions CI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--base-ref` CLI flag and GitHub Actions CI integration (composite action + workflow) so the enforcer runs in CI with changed-files and full-scan modes.

**Architecture:** CLI gains `--base-ref` and `--output` options. `--base-ref` computes diff against a git ref (instead of `--cached`), setting `changed_lines` so `diff_only` rules fire in CI. Composite action wraps the CLI with SARIF output. Workflow runs two jobs: changed-files on feature pushes, full-scan on PR/master.

**Tech Stack:** Python 3.11, Click, GitHub Actions (composite action, workflows), SARIF

---

## File Structure

- Modify: `enforcer/cli.py` — add `--base-ref` and `--output` options, generalize helpers
- Modify: `tests/test_cli_refactor.py` — add tests for `--base-ref` and `--output`
- Create: `.github/actions/enforcer/action.yml` — composite action
- Create: `.github/workflows/enforcer.yml` — CI workflow

---

### Task 1: Add `--output` Option to `check` Command

**Files:**
- Modify: `enforcer/cli.py:99-158`
- Test: `tests/test_cli_refactor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_refactor.py`:

```python
def test_check_output_writes_file(tmp_path):
    """--output should write results to file instead of stdout."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    outfile = tmp_path / "results.txt"
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--paths", "nonexistent.py", "--output", str(outfile)])
    assert result.exit_code == 0
    assert outfile.exists()
    assert "No issues found" in outfile.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_refactor.py::test_check_output_writes_file -v`
Expected: FAIL — `--output` not recognized (Click error: no such option)

- [ ] **Step 3: Add `--output` option to `check` command**

In `enforcer/cli.py`, add the option decorator to `check` (after `--fix`):

```python
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
```

Update the `check` function signature:

```python
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings, fix, output):
```

Replace the output section at end of `check()`:

```python
    reporter = Reporter(format=fmt)
    output_text = reporter.render(all_matches, severity_actions=config.severity_actions)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_text)
    else:
        click.echo(output_text)
    sys.exit(reporter.exit_code(all_matches, severity_actions=config.severity_actions, confirm_warnings=confirm_read_warnings))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_refactor.py::test_check_output_writes_file -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add enforcer/cli.py tests/test_cli_refactor.py
git commit -m "feat(cli): add --output option to check command"
```

---

### Task 2: Generalize `_parse_diff_changed_lines` to Accept a Ref

**Files:**
- Modify: `enforcer/cli.py:27-51`
- Test: `tests/test_cli_refactor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_refactor.py`:

```python
def test_parse_diff_changed_lines_with_ref():
    """Should use <ref>...HEAD when ref is provided."""
    from enforcer.cli import _parse_diff_changed_lines
    diff_output = b"@@ -1,2 +3,2 @@\n-old\n+new\n+newer\n"
    with patch("subprocess.run", return_value=type("R", (), {"returncode": 0, "stdout": diff_output.decode()})()) as mock_run:
        result = _parse_diff_changed_lines(".", "file.py", ref="origin/master")
        assert result == {3, 4}
        # Verify git command used ref, not --cached
        cmd = mock_run.call_args[0][0]
        assert "origin/master...HEAD" in cmd
        assert "--cached" not in cmd


def test_parse_diff_changed_lines_staged_no_ref():
    """Should use --cached when ref is None."""
    from enforcer.cli import _parse_diff_changed_lines
    diff_output = b"@@ -1,0 +2,0 @@\n"
    with patch("subprocess.run", return_value=type("R", (), {"returncode": 0, "stdout": diff_output.decode()})()) as mock_run:
        _parse_diff_changed_lines(".", "file.py", ref=None)
        cmd = mock_run.call_args[0][0]
        assert "--cached" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_refactor.py::test_parse_diff_changed_lines_with_ref tests/test_cli_refactor.py::test_parse_diff_changed_lines_staged_no_ref -v`
Expected: FAIL — `ref` parameter doesn't exist (TypeError)

- [ ] **Step 3: Generalize the function**

Replace `_parse_diff_changed_lines` in `enforcer/cli.py:27-51`:

```python
def _parse_diff_changed_lines(repo_root: str, file_path: str, ref: str | None = None) -> set[int] | None:
    """Parse git diff -U0 for a file, return set of changed (added) line numbers.
    ref=None uses --cached (staged). ref set uses <ref>...HEAD.
    Returns None if diff can't be parsed (no diff info). Returns empty set if diff parsed but no added lines."""
    try:
        diff_cmd = ["git", "diff", "-U0"]
        diff_cmd += ["--cached"] if ref is None else [f"{ref}...HEAD"]
        diff_cmd += ["--", file_path]
        result = subprocess.run(
            diff_cmd,
            capture_output=True, text=True, cwd=repo_root,
        )
        if result.returncode != 0 or not result.stdout:
            return None
    except Exception:
        return None

    import re
    changed: set[int] = set()
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            m = re.search(r'\+(\d+)(?:,(\d+))?', line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                for i in range(start, start + count):
                    changed.add(i)
    return changed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_refactor.py::test_parse_diff_changed_lines_with_ref tests/test_cli_refactor.py::test_parse_diff_changed_lines_staged_no_ref -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add enforcer/cli.py tests/test_cli_refactor.py
git commit -m "feat(cli): generalize _parse_diff_changed_lines to accept git ref"
```

---

### Task 3: Add `--base-ref` Option and Wire Through Helpers

**Files:**
- Modify: `enforcer/cli.py:53-69` (`_collect_files`), `enforcer/cli.py:85-97` (`_run_checks`), `enforcer/cli.py:99-158` (`check`)
- Test: `tests/test_cli_refactor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_refactor.py`:

```python
def test_collect_files_base_ref():
    """Should return file list from git diff <ref>...HEAD when base_ref provided."""
    with patch("subprocess.check_output", return_value=b"changed.py\nother.py\n"):
        result = _collect_files(staged=False, all_files=False, paths=(), ws=".", base_ref="origin/master")
        assert result == ["changed.py", "other.py"]


def test_run_checks_with_diff_ref():
    """Should set changed_lines when diff_ref is provided."""
    from enforcer.types import FileContext, Match, Severity
    from enforcer.context import FileContextBuilder
    from enforcer.runner import RuleRunner
    from enforcer.rule import Rule

    rule = Rule(
        id="test",
        severity=Severity.WARN,
        matchers=[],
        file_globs=["**/*.py"],
    )
    runner = RuleRunner([rule], workspace=".")
    builder = FileContextBuilder([rule], workspace=".")
    with patch("enforcer.cli._parse_diff_changed_lines", return_value={5, 6}):
        matches = _run_checks(runner, builder, ["test.py"], {}, ".", staged=False, diff_ref="origin/master")
    assert isinstance(matches, list)


def test_check_base_ref_mutual_exclusion():
    """--base-ref with --staged should error."""
    from click.testing import CliRunner
    from enforcer.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--staged", "--base-ref", "origin/master"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_refactor.py::test_collect_files_base_ref tests/test_cli_refactor.py::test_run_checks_with_diff_ref tests/test_cli_refactor.py::test_check_base_ref_mutual_exclusion -v`
Expected: FAIL — `base_ref` and `diff_ref` params don't exist

- [ ] **Step 3: Add `base_ref` param to `_collect_files`**

In `enforcer/cli.py:53`, update signature and add branch:

```python
def _collect_files(staged: bool, all_files: bool, paths: tuple, ws: str, base_ref: str | None = None) -> list[str]:
    """Collect the list of files to check based on CLI mode."""
    if staged:
        result = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            stderr=subprocess.DEVNULL, cwd=ws,
        )
        return result.decode().strip().split("\n") if result.strip() else []
    if base_ref:
        result = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            stderr=subprocess.DEVNULL, cwd=ws,
        )
        return result.decode().strip().split("\n") if result.strip() else []
    if all_files:
        file_list = []
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if not _glob_any_match(d, _JUNK_DIRS)]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ws)
                file_list.append(rel)
        return file_list
    return list(paths)
```

- [ ] **Step 4: Add `diff_ref` param to `_run_checks`**

In `enforcer/cli.py:85`, update signature and body:

```python
def _run_checks(runner, builder, file_list: list[str], shared_ctx: dict, ws: str, staged: bool, diff_ref: str | None = None) -> list:
    """Run rules against each file, return aggregated matches."""
    from enforcer.types import Match
    all_matches: list[Match] = []
    for f in file_list:
        if not f:
            continue
        ctx = builder.build(f)
        if diff_ref is not None:
            ctx.changed_lines = _parse_diff_changed_lines(ws, f, ref=diff_ref)
        elif staged:
            ctx.changed_lines = _parse_diff_changed_lines(ws, f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)
    return all_matches
```

- [ ] **Step 5: Add `--base-ref` option and mutual exclusion to `check`**

In `enforcer/cli.py`, add the option decorator (after `--output`):

```python
@click.option("--base-ref", default=None, help="Git ref to diff against (e.g. origin/master). Sets changed_lines so diff_only rules fire in CI.")
```

Update the `check` function signature:

```python
def check(staged, all_files, paths, fmt, config_path, workspace, severity, no_llm, rule_id, confirm_read_warnings, fix, output, base_ref):
    """Check files for convention violations."""
    from enforcer.types import Severity

    exclusive = sum([bool(staged), bool(base_ref), bool(all_files)])
    if exclusive > 1:
        click.echo("Error: --staged, --base-ref, and --all are mutually exclusive.", err=True)
        sys.exit(2)

    config = load_config(config_path)
```

Update the `_collect_files` and `_run_checks` calls:

```python
    file_list = _collect_files(staged, all_files, paths, ws, base_ref=base_ref)
```

```python
    all_matches = _run_checks(runner, builder, file_list, shared_ctx, ws, staged, diff_ref=base_ref)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli_refactor.py -v`
Expected: All tests pass

- [ ] **Step 7: Run full test suite + enforcer self-check**

Run: `pytest --tb=short -q`
Run: `python -m enforcer.cli check --staged`
Expected: All tests pass, 0 enforcer violations

- [ ] **Step 8: Commit**

```bash
git add enforcer/cli.py tests/test_cli_refactor.py
git commit -m "feat(cli): add --base-ref flag for CI diff support"
```

---

### Task 4: Create Composite Action

**Files:**
- Create: `.github/actions/enforcer/action.yml`

- [ ] **Step 1: Verify directory structure**

Run: `ls .github/` (should not exist)

- [ ] **Step 2: Create composite action**

Create `.github/actions/enforcer/action.yml`:

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
      id: run-enforcer
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

- [ ] **Step 3: Commit**

```bash
git add .github/actions/enforcer/action.yml
git commit -m "feat(ci): add composite action for enforcer"
```

---

### Task 5: Create CI Workflow

**Files:**
- Create: `.github/workflows/enforcer.yml`

- [ ] **Step 1: Create workflow**

Create `.github/workflows/enforcer.yml`:

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
    permissions:
      contents: read
      security-events: write
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
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - name: build-wheel
        run: pip install build && python -m build --wheel
      - uses: ./.github/actions/enforcer
        with:
          install-method: wheel
          base-ref: ""
```

- [ ] **Step 2: Run full test suite + enforcer self-check**

Run: `pytest --tb=short -q`
Run: `python -m enforcer.cli check --staged`
Expected: All tests pass, 0 enforcer violations

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/enforcer.yml
git commit -m "feat(ci): add enforcer workflow with changed/full scan jobs"
```

---

### Task 6: Verify Locally

**Files:**
- None (verification only)

- [ ] **Step 1: Test --output flag**

Run: `python -m enforcer.cli check --paths enforcer/cli.py --output /tmp/test-output.txt`
Expected: Exit 0, file `/tmp/test-output.txt` created

- [ ] **Step 2: Test --base-ref flag**

Run: `python -m enforcer.cli check --base-ref HEAD~1 --severity error --no-llm`
Expected: Runs against changed files vs HEAD~1

- [ ] **Step 3: Test mutual exclusion**

Run: `python -m enforcer.cli check --staged --base-ref HEAD~1`
Expected: Exit 2, "mutually exclusive" error message

- [ ] **Step 4: Test SARIF output**

Run: `python -m enforcer.cli check --paths enforcer/cli.py --format sarif --output /tmp/test.sarif`
Expected: Valid JSON SARIF file at `/tmp/test.sarif`

- [ ] **Step 5: Final test suite run**

Run: `pytest --tb=short -q`
Expected: All tests pass
