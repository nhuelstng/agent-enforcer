# WARN Checklist + Scan Mode — Design

**Date:** 2026-06-30
**Status:** Approved (pending spec review)
**Branch:** `feature/pr-comment-posting` (incremental)

## Problem

The PR comment posting feature only runs `--all --severity error`, which:
1. Suppresses `diff_only=True` rules (no `changed_lines` in `--all` mode)
2. Filters out WARN severity (ERROR only)
3. Provides no actionable checklist for agents

The user wants WARN rules (critical-component reminders) to fire on PRs as a checklist, with the ability to choose between full-repo ERROR scanning and diff-based ERROR+WARN scanning.

## Decisions (locked during brainstorm)

| Decision | Choice |
|----------|--------|
| Scan mode | Configurable via `workflow_dispatch` input: `all` (full repo, ERROR only) or `diff` (PR diff, ERROR + WARN) |
| Default scan mode | `diff` |
| Checklist location | Markdown checkboxes in summary comment |
| Checklist persistence | Preserve checked state across re-runs |
| WARN inline comments | Yes — same dedup + posting as ERROR |

## Architecture

### Changes to existing files

```
scripts/pr_commenter.py        # summary_body: checklist section + mode + checked param
                               # extract_checked_items: parse old summary for [x] state
                               # upsert_summary: thread mode + parse before edit
                               # post_comments: thread mode param
scripts/post_pr_comments.py    # main: --mode CLI arg
.github/workflows/enforcer.yml # scan_mode dispatch input + conditional run-enforcer args
tests/test_pr_commenter.py     # 8 new tests
tests/test_post_pr_comments.py # update existing tests for --mode arg
```

No new files. All changes are modifications to existing modules.

## Component Design

### Workflow Configuration

New `scan_mode` dispatch input:

```yaml
on:
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

`run-enforcer` step becomes conditional:

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

`post-comments` step passes mode:

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

### Summary Comment Format

#### Non-empty (with both ERROR + WARN):

```markdown
<!-- enforcer-summary -->
## Enforcer Scan Results

Scan of `{sha}` on {date UTC} (mode: {mode}).

**{N} ERROR** · **{M} WARN** · **{K} INFO**

<details>
<summary>Violations</summary>

| Severity | Rule | File:Line | Message |
|----------|------|-----------|---------|
| ERROR | `no-print` | `src/app.py:42` | Print statements not allowed |
| WARN | `verify-types-changed` | `enforcer/types.py:15` | Core types changed. Run full test suite |
| ... | | | |

</details>

## WARN Checklist

- [ ] `verify-types-changed` — `enforcer/types.py:15` — Core types changed. Run full test suite: pytest --tb=short -q
- [ ] `verify-runner-changed` — `enforcer/runner.py:8` — Runner changed. Run: pytest tests/test_runner.py
- [ ] `verify-context-changed` — `enforcer/context.py:22` — Parse-once cache changed. Verify AST caching

Inline comments posted for each anchorable violation. Re-run to refresh.
```

#### Zero violations:

```markdown
<!-- enforcer-summary -->
## Enforcer Scan Results

Scan of `{sha}` on {date UTC} (mode: {mode}).

No violations found. ✅
```

No checklist section when zero WARN violations.

### Preserve Checked State

On re-runs, `upsert_summary` parses the existing comment body before replacing it.

#### New constant

```python
CHECKED_RE = re.compile(
    r"^- \[x\] `(\S+)` — `([^:]+):(\d+)`",
    re.IGNORECASE | re.MULTILINE,
)
```

#### New function: `extract_checked_items(body) -> set[tuple[str, str, int]]`

```python
def extract_checked_items(body: str) -> set[tuple[str, str, int]]:
    """Extract (rule_id, file, line) from checked checkboxes in summary body."""
    keys = set()
    for m in CHECKED_RE.finditer(body):
        keys.add((m.group(1), m.group(2), int(m.group(3))))
    return keys
```

#### `summary_body` signature change

New `mode` and `checked` params:

```python
def summary_body(
    violations: list[dict],
    sha: str,
    mode: str = "diff",
    now: datetime | None = None,
    checked: set[tuple[str, str, int]] | None = None,
) -> str:
```

Checklist rendering:

```python
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
            checklist_lines.append(f"- [{box}] `{rule}` — `{path}:{line}` — {msg}")
        checklist = "\n".join(checklist_lines)
```

#### `upsert_summary` change

Before calling `comment.edit(body)`, parse old body:

```python
def upsert_summary(repo, pr, violations, sha, mode="diff", now=None):
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

#### `post_comments` change

Threads `mode` through to `upsert_summary`:

```python
def post_comments(repo, pr, violations, sha, mode="diff", now=None):
    summary_url = upsert_summary(repo, pr, violations, sha, mode=mode, now=now)
    posted, skipped = post_inline_comments(repo, pr, violations, sha)
    return posted, skipped, summary_url
```

### Inline Comments for WARN

No change to `inline_body` — already renders severity, message, fix_instruction. WARN inline comments post identically to ERROR, just with `(WARN)` in body.

`post_inline_comments` unchanged — already iterates all violations regardless of severity. WARN violations with valid `file` + `line` get inline comments. File-level WARN violations (line=0) go to summary only.

Dedup logic unchanged — `(path, line, rule_id)` set applies to all severities.

### `post_pr_comments.py` CLI change

New `--mode` arg:

```python
    parser.add_argument("--mode", default="diff", choices=["all", "diff"])
```

Passed to `post_comments`:

```python
    posted, skipped, summary_url = post_comments(repo, pr, violations, args.sha, mode=args.mode)
```

### Tests

#### `tests/test_pr_commenter.py` — 8 new tests

1. **`test_summary_body_warn_checklist`** — WARN items render as `- [ ]` checkboxes in checklist section
2. **`test_summary_body_no_checklist_when_zero_warn`** — ERROR-only violations, no checklist section
3. **`test_summary_body_mode_in_header`** — mode string `(mode: diff)` appears in header
4. **`test_extract_checked_items`** — parses `- [x]` lines, returns set of `(rule_id, file, line)` triplets
5. **`test_extract_checked_items_empty`** — no checked items in body returns empty set
6. **`test_summary_body_preserves_checked_state`** — items in `checked` set render as `- [x]`
7. **`test_upsert_summary_preserves_checked_state`** — old body parsed, checked items carried forward into new body
8. **`test_upsert_summary_no_existing_comment`** — first run (no existing comment), all items unchecked

#### `tests/test_post_pr_comments.py` — modify existing

Existing tests updated to pass `--mode diff` where needed (or verify default works without explicit flag).

## Edge Cases

| Case | Handling |
|------|----------|
| WARN item no longer present on re-run (file fixed) | Dropped from checklist. Correct — no longer relevant. |
| New WARN item on re-run | Starts unchecked. |
| No existing comment (first run) | `checked` is empty set. All items unchecked. |
| Manual edit garbled checkbox | Regex won't match, item treated as unchecked. Safe fallback. |
| Zero WARN violations | No checklist section rendered. Summary still shows violation table. |
| Zero violations total | "No violations found. ✅" body, no checklist. |
| `all` mode (ERROR only) | No WARN items, no checklist. Mode string shows `(mode: all)`. |
| WARN violation with `line=0` (file-level) | Appears in checklist (uses `file:0`). Not posted as inline comment (existing file-level skip). |
| WARN violation with `file=None` | Appears in checklist with `file=?`. Not posted as inline comment. |

## Dependencies

No new dependencies. All changes use stdlib (`re`) and existing PyGithub patterns.

## Out of Scope

- Automatic checkbox checking based on test run results
- Checklist items for INFO severity
- Separate checklist comment (single updatable summary chosen)
- Resolving inline threads for fixed violations
