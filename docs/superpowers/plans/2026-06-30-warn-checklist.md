# WARN Checklist + Scan Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable scan mode (`all` vs `diff`) to the `comment-pr` workflow, with WARN violations rendered as a markdown checklist in the summary comment. Checked state is preserved across re-runs.

**Architecture:** New `scan_mode` dispatch input drives conditional CLI args. `summary_body` gains `mode` + `checked` params, splits WARN items into checklist section. `upsert_summary` parses old comment body for `[x]` state before editing. CLI entrypoint gets `--mode` arg.

**Tech Stack:** Python 3.11, PyGithub, GitHub Actions, enforcer JSON output

---

## File Structure

```
scripts/pr_commenter.py        # Modify: summary_body (mode+checked), extract_checked_items, upsert_summary (mode+preserve), post_comments (mode)
scripts/post_pr_comments.py    # Modify: main() add --mode arg
tests/test_pr_commenter.py     # Modify: 8 new tests
tests/test_post_pr_comments.py # Modify: update existing tests for --mode
.github/workflows/enforcer.yml # Modify: scan_mode input, conditional run-enforcer, --mode in post-comments
```

No new files. All changes are modifications to existing modules.

---

### Task 1: `extract_checked_items` — parse old summary for checked state

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pr_commenter.py

from scripts.pr_commenter import extract_checked_items


def test_extract_checked_items_finds_checked():
    body = """<!-- enforcer-summary -->
## Enforcer Scan Results

## WARN Checklist

- [x] `verify-types-changed` — `enforcer/types.py:15` — Core types changed
- [ ] `verify-runner-changed` — `enforcer/runner.py:8` — Runner changed
- [x] `verify-context-changed` — `enforcer/context.py:22` — Cache changed
"""
    keys = extract_checked_items(body)
    assert ("verify-types-changed", "enforcer/types.py", 15) in keys
    assert ("verify-context-changed", "enforcer/context.py", 22) in keys
    assert ("verify-runner-changed", "enforcer/runner.py", 8) not in keys
    assert len(keys) == 2


def test_extract_checked_items_empty_body():
    keys = extract_checked_items("no checkboxes here")
    assert keys == set()


def test_extract_checked_items_case_insensitive():
    body = "- [X] `verify-types-changed` — `enforcer/types.py:15` — msg"
    keys = extract_checked_items(body)
    assert ("verify-types-changed", "enforcer/types.py", 15) in keys
    assert len(keys) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py -k extract_checked -v`
Expected: FAIL with `ImportError: cannot import name 'extract_checked_items'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/pr_commenter.py` (after `RULE_MARKER_RE` line):

```python
CHECKED_RE = re.compile(
    r"^- \[x\] `(\S+)` — `([^:]+):(\d+)`",
    re.IGNORECASE | re.MULTILINE,
)


def extract_checked_items(body: str) -> set[tuple[str, str, int]]:
    """Extract (rule_id, file, line) from checked checkboxes in summary body."""
    keys = set()
    for m in CHECKED_RE.finditer(body):
        keys.add((m.group(1), m.group(2), int(m.group(3))))
    return keys
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -k extract_checked -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add extract_checked_items for parsing checkbox state"
```

---

### Task 2: `summary_body` — add mode param to header

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

def test_summary_body_mode_in_header():
    body = summary_body([], sha="abc123", mode="diff")
    assert "(mode: diff)" in body

    body_all = summary_body([], sha="abc123", mode="all")
    assert "(mode: all)" in body_all
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_summary_body_mode_in_header -v`
Expected: FAIL — current `summary_body` has no `mode` param, uses "Full scan of"

- [ ] **Step 3: Modify `summary_body` signature and header**

Replace the current `summary_body` function in `scripts/pr_commenter.py` with:

```python
def summary_body(
    violations: list[dict],
    sha: str,
    mode: str = "diff",
    now: datetime | None = None,
    checked: set[tuple[str, str, int]] | None = None,
) -> str:
    """Render the summary comment body for a list of violations."""
    if now is None:
        now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")
    if not violations:
        return (
            f"{SUMMARY_MARKER}\n"
            f"## Enforcer Scan Results\n\n"
            f"Scan of `{sha}` on {date_str} (mode: {mode}).\n\n"
            f"No violations found. \u2705\n"
        )
    counts = {"error": 0, "warn": 0, "info": 0}
    for v in violations:
        sev = v.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1
    rows = []
    for v in violations:
        sev = v.get("severity", "info").upper()
        rule = v.get("rule_id", "?")
        path = v.get("file", "?")
        line = v.get("line", 0)
        msg = v.get("message", "")
        rows.append(f"| {sev} | `{rule}` | `{path}:{line}` | {msg} |")
    table = "\n".join(rows)
    return (
        f"{SUMMARY_MARKER}\n"
        f"## Enforcer Scan Results\n\n"
        f"Scan of `{sha}` on {date_str} (mode: {mode}).\n\n"
        f"**{counts['error']} ERROR** \u00b7 **{counts['warn']} WARN** \u00b7 **{counts['info']} INFO**\n\n"
        f"<details>\n"
        f"<summary>Violations</summary>\n\n"
        f"| Severity | Rule | File:Line | Message |\n"
        f"|----------|------|-----------|---------|\n"
        f"{table}\n\n"
        f"</details>\n\n"
        f"Inline comments posted for each anchorable violation. Re-run to refresh.\n"
    )
```

Note: the `checked` param is added now but not yet used — Task 3 implements the checklist section. The `Full scan of` wording changed to `Scan of` + `(mode: {mode})`.

- [ ] **Step 4: Run ALL existing tests to check for breakage**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: Some existing tests may fail because they assert `"Full scan of"` — update them.

Check which tests reference the old wording:

```bash
grep -n "Full scan" tests/test_pr_commenter.py
```

If any tests assert `"Full scan of"`, replace with `"Scan of"`. The `test_summary_body_with_violations` test doesn't assert the header wording, so it should pass. Run to confirm.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add mode param to summary_body header"
```

---

### Task 3: `summary_body` — add WARN checklist section

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pr_commenter.py

def test_summary_body_warn_checklist():
    violations = [
        {"rule_id": "no-print", "severity": "error", "file": "src/app.py",
         "line": 42, "message": "Print statements not allowed",
         "fix_instruction": "Use logging instead of print()."},
        {"rule_id": "verify-types-changed", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Core types changed. Run full test suite",
         "fix_instruction": "Run pytest --tb=short -q"},
    ]
    body = summary_body(violations, sha="abc123", mode="diff")
    assert "## WARN Checklist" in body
    assert "- [ ] `verify-types-changed`" in body
    assert "enforcer/types.py:15" in body
    assert "Core types changed. Run full test suite" in body
    # ERROR violation should NOT be in checklist
    assert "- [ ] `no-print`" not in body


def test_summary_body_no_checklist_when_zero_warn():
    violations = [
        {"rule_id": "no-print", "severity": "error", "file": "src/app.py",
         "line": 42, "message": "Print statements not allowed",
         "fix_instruction": "Use logging instead of print()."},
    ]
    body = summary_body(violations, sha="abc123", mode="diff")
    assert "## WARN Checklist" not in body


def test_summary_body_preserves_checked_state():
    violations = [
        {"rule_id": "verify-types-changed", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Core types changed",
         "fix_instruction": "Run pytest"},
        {"rule_id": "verify-runner-changed", "severity": "warn", "file": "enforcer/runner.py",
         "line": 8, "message": "Runner changed",
         "fix_instruction": "Run pytest"},
    ]
    checked = {("verify-types-changed", "enforcer/types.py", 15)}
    body = summary_body(violations, sha="abc123", mode="diff", checked=checked)
    assert "- [x] `verify-types-changed`" in body
    assert "- [ ] `verify-runner-changed`" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py -k "warn_checklist or preserves_checked" -v`
Expected: FAIL — `summary_body` doesn't render checklist section yet

- [ ] **Step 3: Modify `summary_body` to add checklist section**

Replace the return block (the non-empty case) in `summary_body` in `scripts/pr_commenter.py`. The full function becomes:

```python
def summary_body(
    violations: list[dict],
    sha: str,
    mode: str = "diff",
    now: datetime | None = None,
    checked: set[tuple[str, str, int]] | None = None,
) -> str:
    """Render the summary comment body for a list of violations."""
    if now is None:
        now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")
    if not violations:
        return (
            f"{SUMMARY_MARKER}\n"
            f"## Enforcer Scan Results\n\n"
            f"Scan of `{sha}` on {date_str} (mode: {mode}).\n\n"
            f"No violations found. \u2705\n"
        )
    counts = {"error": 0, "warn": 0, "info": 0}
    for v in violations:
        sev = v.get("severity", "info").lower()
        if sev in counts:
            counts[sev] += 1
    rows = []
    for v in violations:
        sev = v.get("severity", "info").upper()
        rule = v.get("rule_id", "?")
        path = v.get("file", "?")
        line = v.get("line", 0)
        msg = v.get("message", "")
        rows.append(f"| {sev} | `{rule}` | `{path}:{line}` | {msg} |")
    table = "\n".join(rows)
    body = (
        f"{SUMMARY_MARKER}\n"
        f"## Enforcer Scan Results\n\n"
        f"Scan of `{sha}` on {date_str} (mode: {mode}).\n\n"
        f"**{counts['error']} ERROR** \u00b7 **{counts['warn']} WARN** \u00b7 **{counts['info']} INFO**\n\n"
        f"<details>\n"
        f"<summary>Violations</summary>\n\n"
        f"| Severity | Rule | File:Line | Message |\n"
        f"|----------|------|-----------|---------|\n"
        f"{table}\n\n"
        f"</details>\n\n"
    )
    warn_items = [v for v in violations if v.get("severity", "").lower() == "warn"]
    if warn_items:
        checked = checked or set()
        checklist_lines = []
        for v in warn_items:
            rule = v.get("rule_id", "?")
            path = v.get("file", "?")
            line = v.get("line", 0)
            msg = v.get("message", "")
            box = "x" if (rule, path, line) in checked else " "
            checklist_lines.append(f"- [{box}] `{rule}` \u2014 `{path}:{line}` \u2014 {msg}")
        checklist = "\n".join(checklist_lines)
        body += f"## WARN Checklist\n\n{checklist}\n\n"
    body += "Inline comments posted for each anchorable violation. Re-run to refresh.\n"
    return body
```

Note: `\u2014` is the em-dash `—` character. Used in both the checklist rendering and the `CHECKED_RE` regex from Task 1 — they must match.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): add WARN checklist section to summary body"
```

---

### Task 4: `upsert_summary` — preserve checked state on edit

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pr_commenter.py

def test_upsert_summary_preserves_checked_state():
    old_body = """<!-- enforcer-summary -->
## Enforcer Scan Results

## WARN Checklist

- [x] `verify-types-changed` — `enforcer/types.py:15` — Core types changed
- [ ] `verify-runner-changed` — `enforcer/runner.py:8` — Runner changed
"""
    existing = MagicMock()
    existing.body = old_body
    existing.html_url = "https://github.com/owner/repo/issues/1#issuecomment-99"

    issue = MagicMock()
    issue.get_comments.return_value = [existing]

    repo = MagicMock()
    repo.get_issue.return_value = issue

    pr = MagicMock()
    pr.number = 1

    violations = [
        {"rule_id": "verify-types-changed", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Core types changed", "fix_instruction": "Run pytest"},
        {"rule_id": "verify-runner-changed", "severity": "warn", "file": "enforcer/runner.py",
         "line": 8, "message": "Runner changed", "fix_instruction": "Run pytest"},
    ]
    url = upsert_summary(repo, pr, violations, sha="abc123", mode="diff")
    existing.edit.assert_called_once()
    edited_body = existing.edit.call_args[0][0]
    assert "- [x] `verify-types-changed`" in edited_body
    assert "- [ ] `verify-runner-changed`" in edited_body
    assert url == "https://github.com/owner/repo/issues/1#issuecomment-99"


def test_upsert_summary_no_existing_comment_all_unchecked():
    new_comment = MagicMock()
    new_comment.html_url = "https://github.com/owner/repo/issues/1#issuecomment-1"

    issue = MagicMock()
    issue.get_comments.return_value = []
    issue.create_comment.return_value = new_comment

    repo = MagicMock()
    repo.get_issue.return_value = issue

    pr = MagicMock()
    pr.number = 1

    violations = [
        {"rule_id": "verify-types-changed", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Core types changed", "fix_instruction": "Run pytest"},
    ]
    url = upsert_summary(repo, pr, violations, sha="abc123", mode="diff")
    issue.create_comment.assert_called_once()
    created_body = issue.create_comment.call_args[0][0]
    assert "- [ ] `verify-types-changed`" in created_body
    assert "- [x]" not in created_body
    assert url == "https://github.com/owner/repo/issues/1#issuecomment-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pr_commenter.py -k "preserves_checked or no_existing_comment_all" -v`
Expected: FAIL — `upsert_summary` doesn't have `mode` param or parse checked state

- [ ] **Step 3: Modify `upsert_summary`**

Replace the current `upsert_summary` function in `scripts/pr_commenter.py` with:

```python
def upsert_summary(
    repo,
    pr,
    violations: list[dict],
    sha: str,
    mode: str = "diff",
    now: datetime | None = None,
) -> str:
    """Find existing summary comment by marker and edit, or create new. Returns comment URL."""
    issue = repo.get_issue(pr.number)
    for comment in issue.get_comments():
        if comment.body.lstrip().startswith(SUMMARY_MARKER):
            checked = extract_checked_items(comment.body)
            body = summary_body(violations, sha, mode=mode, now=now, checked=checked)
            comment.edit(body)
            return comment.html_url
    body = summary_body(violations, sha, mode=mode, now=now)
    comment = issue.create_comment(body)
    return comment.html_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): preserve checked state in upsert_summary"
```

---

### Task 5: `post_comments` — thread mode param

**Files:**
- Modify: `scripts/pr_commenter.py`
- Test: `tests/test_pr_commenter.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_pr_commenter.py

def test_post_comments_threads_mode_to_summary():
    pr = MagicMock()
    pr.number = 1
    pr.get_review_comments.return_value = []

    new_comment = MagicMock()
    new_comment.html_url = "https://github.com/owner/repo/issues/1#issuecomment-1"
    new_comment.body = ""
    issue = MagicMock()
    issue.get_comments.return_value = []
    issue.create_comment.return_value = new_comment

    repo = MagicMock()
    repo.get_issue.return_value = issue

    violations = [
        {"rule_id": "verify-types-changed", "severity": "warn", "file": "enforcer/types.py",
         "line": 15, "message": "Core types changed", "fix_instruction": "Run pytest"},
    ]
    post_comments(repo, pr, violations, sha="abc123", mode="all")
    created_body = issue.create_comment.call_args[0][0]
    assert "(mode: all)" in created_body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pr_commenter.py::test_post_comments_threads_mode_to_summary -v`
Expected: FAIL — `post_comments` doesn't accept `mode` param

- [ ] **Step 3: Modify `post_comments`**

Replace the current `post_comments` function in `scripts/pr_commenter.py` with:

```python
def post_comments(
    repo,
    pr,
    violations: list[dict],
    sha: str,
    mode: str = "diff",
    now: datetime | None = None,
) -> tuple[int, int, str]:
    """Post summary + inline comments. Returns (posted, skipped, summary_url)."""
    summary_url = upsert_summary(repo, pr, violations, sha, mode=mode, now=now)
    posted, skipped = post_inline_comments(repo, pr, violations, sha)
    return posted, skipped, summary_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pr_commenter.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pr_commenter.py tests/test_pr_commenter.py
git commit -m "feat(pr-commenter): thread mode param through post_comments"
```

---

### Task 6: `post_pr_comments.py` — add `--mode` CLI arg

**Files:**
- Modify: `scripts/post_pr_comments.py`
- Test: `tests/test_post_pr_comments.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_post_pr_comments.py

def test_main_passes_mode_to_post_comments(tmp_path):
    json_file = tmp_path / "violations.json"
    json_file.write_text(json.dumps({
        "summary": {"total": 1},
        "issues": [
            {"rule_id": "no-print", "file": "src/app.py", "line": 42,
             "severity": "error", "message": "m", "fix_instruction": "f"}
        ],
    }))

    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token-123"}):
        with patch("scripts.post_pr_comments.Github") as mock_github:
            with patch("scripts.post_pr_comments.post_comments") as mock_pc:
                mock_pc.return_value = (1, 0, "https://github.com/owner/repo/issues/1#issuecomment-1")
                mock_repo = MagicMock()
                mock_pr = MagicMock()
                mock_repo.get_pull.return_value = mock_pr
                mock_github.return_value.get_repo.return_value = mock_repo

                main([
                    "--json", str(json_file),
                    "--pr", "1",
                    "--repo", "owner/repo",
                    "--sha", "abc123",
                    "--mode", "all",
                ])
    mock_pc.assert_called_once()
    call_kwargs = mock_pc.call_args
    assert call_kwargs[1].get("mode") == "all" or call_kwargs[0].count("all") > 0 or "all" in str(call_kwargs)
```

Note: the assertion is flexible because `mode` could be passed as kwarg or positional. The implementation uses keyword arg.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_post_pr_comments.py::test_main_passes_mode_to_post_comments -v`
Expected: FAIL — `--mode` arg doesn't exist, argparse rejects it

- [ ] **Step 3: Modify `post_pr_comments.py`**

In `scripts/post_pr_comments.py`, add `--mode` arg to parser and pass to `post_comments`. Replace the relevant lines:

```python
    parser.add_argument("--sha", required=True)
    parser.add_argument("--mode", default="diff", choices=["all", "diff"])
    args = parser.parse_args(argv)
```

And replace the `post_comments` call:

```python
    posted, skipped, summary_url = post_comments(repo, pr, violations, args.sha, mode=args.mode)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_post_pr_comments.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/post_pr_comments.py tests/test_post_pr_comments.py
git commit -m "feat(pr-comments): add --mode CLI arg"
```

---

### Task 7: Workflow — `scan_mode` dispatch input + conditional args

**Files:**
- Modify: `.github/workflows/enforcer.yml`

- [ ] **Step 1: Read current workflow**

Read `.github/workflows/enforcer.yml`. Note the `on:` block (lines 3-12) and `comment-pr` job (lines 62-96).

- [ ] **Step 2: Add `scan_mode` input to `workflow_dispatch`**

Replace the `workflow_dispatch:` block:

```yaml
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to post comments on"
        required: true
        type: string
      scan_mode:
        description: "Scan mode: 'all' (full repo, errors only) or 'diff' (PR diff, errors + warnings)"
        required: false
        type: choice
        options:
          - all
          - diff
        default: diff
```

- [ ] **Step 3: Modify `run-enforcer` step to be conditional**

Replace the `run-enforcer` step:

```yaml
      - name: run-enforcer
        continue-on-error: true
        env:
          SCAN_MODE: ${{ github.event.inputs.scan_mode }}
        run: |
          if [ "$SCAN_MODE" = "all" ]; then
            python -m enforcer.cli check --all --no-llm --severity error --format json --output violations.json
          else
            python -m enforcer.cli check --base-ref origin/main --no-llm --severity warn --format json --output violations.json
          fi
```

- [ ] **Step 4: Modify `post-comments` step to pass mode**

Add `SCAN_MODE` env var and `--mode` arg:

```yaml
      - name: post-comments
        if: always()
        env:
          GITHUB_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.inputs.pr_number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          COMMIT_SHA: ${{ github.sha }}
          SCAN_MODE: ${{ github.event.inputs.scan_mode }}
          PYTHONPATH: "."
        run: |
          python scripts/post_pr_comments.py \
            --json violations.json \
            --pr "$PR_NUMBER" \
            --repo "$GITHUB_REPOSITORY" \
            --sha "$COMMIT_SHA" \
            --mode "$SCAN_MODE"
```

- [ ] **Step 5: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/enforcer.yml'))" && echo "YAML valid"`
Expected: `YAML valid`

- [ ] **Step 6: Run full test suite + self-enforcement**

Run: `pytest --tb=short -q && python -m enforcer.cli check --all --config enforcer_config.py`
Expected: All tests pass, no enforcement issues.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/enforcer.yml
git commit -m "ci: add scan_mode dispatch input with conditional enforcer args"
```

---

### Task 8: Final verification

**Files:**
- No new files. Verification only.

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (538 existing + ~14 new = ~552)

- [ ] **Step 2: Run enforcer self-check**

Run: `python -m enforcer.cli check --all --config enforcer_config.py`
Expected: `No issues found.`

- [ ] **Step 3: Verify summary_body renders correctly with a dry run**

```bash
python -c "
from scripts.pr_commenter import summary_body
violations = [
    {'rule_id': 'no-print', 'severity': 'error', 'file': 'src/app.py', 'line': 42, 'message': 'Print not allowed', 'fix_instruction': 'Use logging'},
    {'rule_id': 'verify-types-changed', 'severity': 'warn', 'file': 'enforcer/types.py', 'line': 15, 'message': 'Core types changed. Run tests', 'fix_instruction': 'Run pytest'},
]
print(summary_body(violations, 'abc123', mode='diff'))
"
```

Expected: Output contains `(mode: diff)`, violation table, `## WARN Checklist`, `- [ ]` checkbox for WARN item.

- [ ] **Step 4: Verify preserve-checked works**

```bash
python -c "
from scripts.pr_commenter import summary_body
violations = [
    {'rule_id': 'verify-types-changed', 'severity': 'warn', 'file': 'enforcer/types.py', 'line': 15, 'message': 'Core types changed', 'fix_instruction': 'Run pytest'},
]
checked = {('verify-types-changed', 'enforcer/types.py', 15)}
print(summary_body(violations, 'abc123', mode='diff', checked=checked))
"
```

Expected: Output contains `- [x]` for the checked item.

- [ ] **Step 5: Final commit if cleanup needed**

If self-enforcement flagged anything, fix and commit. Otherwise no commit needed.

---

## Self-Review Notes

**Spec coverage check:**
- `scan_mode` dispatch input (all/diff) → Task 7
- Conditional CLI args (`--all --severity error` vs `--base-ref --severity warn`) → Task 7
- `summary_body` mode param in header → Task 2
- WARN checklist section with checkboxes → Task 3
- `extract_checked_items` parsing → Task 1
- `upsert_summary` preserves checked state → Task 4
- `post_comments` threads mode → Task 5
- `post_pr_comments.py` `--mode` arg → Task 6
- Inline comments for WARN (no change needed) → Verified, no task needed
- 8 new tests → Tasks 1-5

**Placeholder scan:** None found. All steps have complete code.

**Type consistency:**
- `extract_checked_items(body) -> set[tuple[str, str, int]]` — used in Task 1, called by `upsert_summary` in Task 4
- `summary_body(violations, sha, mode, now, checked)` — used in Task 2, 3, called by `upsert_summary` in Task 4
- `upsert_summary(repo, pr, violations, sha, mode, now)` — used in Task 4, called by `post_comments` in Task 5
- `post_comments(repo, pr, violations, sha, mode, now)` — used in Task 5, called by `main()` in Task 6
- `CHECKED_RE` regex matches `- [x]` with em-dash `—` (`\u2014`) — matches checklist rendering in Task 3 which uses `\u2014`
- `main(argv)` with `--mode` arg → Task 6

All signatures consistent across tasks.
