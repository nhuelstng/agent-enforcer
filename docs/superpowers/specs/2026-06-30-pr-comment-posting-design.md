# PR Comment Posting — Design

**Date:** 2026-06-30
**Status:** Approved (pending spec review)
**Branch:** TBD

## Problem

Enforcer CI runs produce SARIF output (uploaded to GitHub code scanning) and a pass/fail signal. There is no visible, in-PR feedback for developers who don't check the SARIF tab. A manual trigger is wanted that posts violations as inline PR review comments (anchored to the offending line) plus a summary comment on the PR. Re-triggering must not produce duplicate comments at the same location.

## Decisions (locked during brainstorm)

| Decision | Choice |
|----------|--------|
| Dedup strategy (summary) | Single updatable comment — find by marker, edit in-place |
| Dedup strategy (inline) | Skip if existing unresolved enforcer thread at same (path, line, rule_id) |
| Trigger scope | Manual `workflow_dispatch` only; existing push/PR jobs unchanged |
| Comment content | Inline code comments at violation locations + updatable summary comment |
| Implementation host | Python script + PyGithub library |
| Run target | Full scan (`--all`) on current SHA |
| Secret | `GITHUB_TOKEN` only (auto-provided, `pull-requests: write` permission) |

## Architecture

### Files

```
.github/workflows/enforcer.yml        # new job: comment-pr (workflow_dispatch only)
scripts/post_pr_comments.py           # CLI entrypoint (argparse, I/O, exit codes)
scripts/pr_commenter.py               # PyGithub logic (testable, mockable)
tests/test_pr_commenter.py            # paired unit tests (mock client)
```

Two modules keep concerns separated: `post_pr_comments.py` handles CLI parsing, file loading, and process exit code; `pr_commenter.py` holds all GitHub API logic and is fully unit-testable by mocking the PyGithub client. This mirrors the existing repo pattern of thin CLI entrypoints (`enforcer/cli.py`) delegating to focused logic modules (`enforcer/reporter.py`).

### Data flow

1. Manual `workflow_dispatch` with required input `pr_number`
2. Job checks out repo at current SHA, sets up Python 3.11
3. Builds wheel, installs enforcer + `PyGithub`
4. Runs `python -m enforcer.cli check --all --no-llm --format json --output violations.json`
5. Runs `python scripts/post_pr_comments.py --json violations.json --pr <pr_number> --repo <owner/repo> --sha <sha>`
6. Script loads JSON, initializes PyGithub client with `GITHUB_TOKEN`
7. Script upserts summary comment (find by marker → edit, else create)
8. Script fetches existing inline review comments, builds dedup set
9. Script posts inline comments for violations not in dedup set
10. Script exits non-zero if any violations were found (job shows red = signal)

### JSON input shape

Enforcer JSON output (from `enforcer/reporter.py:_render_json`):

```json
{
  "summary": {"total": 2, "errors": 1, "warnings": 1, "info": 0},
  "issues": [
    {
      "file": "src/app.py",
      "line": 42,
      "column": 5,
      "rule_id": "no-print",
      "severity": "error",
      "message": "Print statements not allowed",
      "matched_value": "print(",
      "fix_instruction": "Use logging instead of print().",
      "llm_response": null
    }
  ]
}
```

The script reads `issues` list. Each issue provides all fields needed for inline + summary comments.

## Component Design

### `scripts/post_pr_comments.py` (entrypoint)

Responsibilities:
- Parse CLI args: `--json` (path), `--pr` (int), `--repo` (owner/repo), `--sha` (commit SHA)
- Load JSON file, extract `issues` list
- Read `GITHUB_TOKEN` env var, initialize `github.Github(token=...)` client
- Call `pr_commenter.post_comments(repo, pr, issues, sha)`
- Print summary (posted count, skipped count, summary URL)
- Exit code: 0 if no issues, 1 if issues found (comments posted either way before exit)

Edge cases:
- Empty `issues` list → print "No violations found", exit 0, no comments posted
- `GITHUB_TOKEN` not set → PyGithub raises on init, script fails with clear message
- PR not found → `repo.get_pull()` raises `UnknownObjectException`, script exits with error

### `scripts/pr_commenter.py` (logic)

Public API:

```python
def post_comments(repo, pr, violations: list[dict], sha: str) -> tuple[int, int, str]:
    """Post summary + inline comments. Returns (posted, skipped, summary_url)."""
```

- `repo`: `github.Repository.Repository` instance (mockable)
- `pr`: `github.PullRequest.PullRequest` instance (mockable)
- `violations`: list of issue dicts (from enforcer JSON `issues` array)
- `sha`: commit SHA (for summary header)

#### Summary comment

Marker: `<!-- enforcer-summary -->` as first line of body.

Upsert logic:
1. List issue comments via `repo.get_issue(pr.number).get_comments()`
2. Find comment where `comment.body.startswith(SUMMARY_MARKER)`
3. If found: `comment.edit(new_body)` → return `comment.html_url`
4. If not: `repo.get_issue(pr.number).create_comment(body)` → return `comment.html_url`

Body template:

```markdown
<!-- enforcer-summary -->
## Enforcer Scan Results

Full scan of `{sha}` on {date UTC}.

**{errors} ERROR** · **{warnings} WARN** · **{info} INFO**

<details>
<summary>Violations</summary>

| Severity | Rule | File:Line | Message |
|----------|------|-----------|---------|
| ERROR | `no-print` | `src/app.py:42` | Print statements not allowed |
| WARN | `core-file-warning` | `enforcer/types.py:15` | Verify tests pass before merging |
| ... | | | |

</details>

Inline comments posted for each anchorable violation. Re-run to refresh.
```

Zero-violation body:

```markdown
<!-- enforcer-summary -->
## Enforcer Scan Results

Full scan of `{sha}` on {date UTC}.

No violations found. ✅
```

#### Inline review comments

Posted via PR review comments API (`pr.create_review_comment`), not the PR review API — individual comments, no pending review state to manage.

Each comment body:

```markdown
<!-- enforcer rule_id={rule_id} -->
**`{rule_id}`** ({severity})

{message}

Fix: {fix_instruction}
```

Anchor: `path=file`, `line=line`, `side="RIGHT"`. Single-line comments (start_line == line).

#### Dedup logic (inline, "skip if existing unresolved")

1. Fetch existing PR review comments: `pr.get_review_comments()`
2. Filter to bot-owned (`c.user.login == "github-actions[bot]"`) AND body matches `RULE_MARKER_RE`
3. Extract `(c.path, c.line, rule_id)` from each. Build set.
4. For each new violation:
   - Compute key `(file, line, rule_id)`
   - Skip if `file` is None/empty, `line` is 0/None (file-level violations — summary only)
   - Skip if key in existing set
   - Else post inline comment
5. Return `(posted_count, skipped_count, summary_url)`

Note on "resolved" threads: GitHub marks resolved threads but the comment resource persists. This design treats **any existing enforcer comment at (path, line, rule_id)** as a duplicate, regardless of resolved state. Rationale: posting to a resolved thread would un-resolve it, creating noise. If a user wants to re-raise a resolved violation, they delete the old comment first, then re-run. This is simpler than querying thread resolution state (which requires additional API calls and pagination of thread metadata).

### `tests/test_pr_commenter.py`

Uses `unittest.mock.MagicMock` to mock `repo` and `pr`. Tests:

1. **`test_summary_body_zero_violations`** — empty list produces "No violations found. ✅" body with marker
2. **`test_summary_body_with_violations`** — counts correct, table rendered, all fields present, collapsible details wrapper
3. **`test_upsert_summary_edits_existing`** — existing comment with marker → `edit()` called, no `create_comment()`
4. **`test_upsert_summary_creates_new`** — no existing marker comment → `create_comment()` called
5. **`test_existing_inline_keys_extracts_triplets`** — bot comments with marker yield (path, line, rule_id) set; non-bot comments ignored; comments without marker ignored
6. **`test_post_comments_skips_duplicates`** — violation matching existing key → skipped, not posted
7. **`test_post_comments_posts_new`** — new violation → `create_review_comment()` called with correct body/path/line
8. **`test_post_comments_skips_file_level`** — `line=0` violation → skipped for inline, still counted in summary
9. **`test_inline_body_has_marker_and_fields`** — body starts with marker, contains rule_id, severity, message, fix_instruction
10. **`test_post_comments_returns_counts`** — returns (posted, skipped, summary_url) tuple correctly

## Workflow Configuration

### New job in `.github/workflows/enforcer.yml`

```yaml
on:
  push:
    branches: [main, "feature/**", "fix/**", "refactor/**", "docs/**", "chore/**"]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to post comments on"
        required: true
        type: string
```

New job:

```yaml
  comment-pr:
    name: post-pr-comments
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: build-wheel
        run: pip install build && python -m build --wheel
      - name: install-deps
        run: pip install dist/*.whl PyGithub
      - name: run-enforcer
        run: |
          python -m enforcer.cli check --all --no-llm --format json --output violations.json
      - name: post-comments
        env:
          GITHUB_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.inputs.pr_number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          COMMIT_SHA: ${{ github.sha }}
        run: |
          python scripts/post_pr_comments.py \
            --json violations.json \
            --pr "$PR_NUMBER" \
            --repo "$GITHUB_REPOSITORY" \
            --sha "$COMMIT_SHA"
```

Note: workflow uses `GITHUB_TOKEN` env var (read by `post_pr_comments.py`, passed to `Github(token=...)`). PyGithub does not auto-read env vars — script must read and pass explicitly.

### Permissions

- `contents: read` — checkout
- `pull-requests: write` — post + edit PR comments (summary + inline)
- No `security-events: write` — no SARIF upload in this job
- No `actions: read` — not needed
- `GITHUB_TOKEN` auto-provided by GitHub Actions. No PAT or extra secret required.

### Exit code behavior

- Enforcer `check --format json` exits 0 (produces output regardless of violations)
- `post_pr_comments.py` exits 1 if any violations were in the JSON (after posting all comments)
- Job shows red when violations exist = signal to developer
- Comments always posted before exit (both summary + inline)

## Edge Cases

| Case | Handling |
|------|----------|
| Violation `line=0` (file-level, e.g. metadata rules) | Include in summary table only, skip inline posting |
| File unchanged in PR diff (GitHub rejects inline comment) | `create_review_comment` raises `UnknownObjectException`; catch per-comment, log warning, continue. Summary still shows it. |
| Not a PR context (dispatch on branch with no PR) | User provides `pr_number` input; if PR doesn't exist, `get_pull()` raises, script exits with error |
| Zero violations | Summary posted with "No violations found ✅", no inline comments, exit 0 |
| `GITHUB_TOKEN` not set | PyGithub raises on init; script fails before posting |
| Large violation count (>100) | Summary table in collapsible `<details>`; inline comments posted one-by-one (GitHub has no batch endpoint for standalone review comments). Acceptable for typical volumes (<50). |
| `fix_instruction` is None/empty | Render "Fix: (none)" in inline body |

## Dependencies

- `PyGithub` — added to CI install step only (`pip install dist/*.whl PyGithub`). Not added to `pyproject.toml` dependencies (CI-only, not a runtime requirement of enforcer itself).
- `GITHUB_TOKEN` — auto-provided by GitHub Actions, no secret configuration needed.

## Out of Scope

- Automatic posting on PR open/sync (manual dispatch only, per decision)
- Resolving/dismissing old inline threads (skip-if-existing strategy chosen)
- Batch posting of inline comments via PR review API (single comments, simpler)
- Posting to non-PR contexts (issues, commits)
- Rate limiting handling beyond PyGithub defaults (low volume expected)
