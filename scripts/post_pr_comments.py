"""Post enforcer violations as PR comments. CI entrypoint."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ponytail: placeholder so tests can patch scripts.post_pr_comments.Github.
# Real import happens lazily inside main() — PyGithub is optional at test time.
Github = None
post_comments = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)

    data = json.loads(args.json.read_text())
    violations = data.get("issues", [])
    if not violations:
        print("No violations found. Nothing to post.")
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN env var not set.", file=sys.stderr)
        return 2

    # Lazy import: tests patch the module-level names above.
    if Github is None:
        from github import Github as _Github  # type: ignore
        globals()["Github"] = _Github
    if post_comments is None:
        from scripts.pr_commenter import post_comments as _post_comments
        globals()["post_comments"] = _post_comments

    gh = Github(login_or_token=token)
    repo = gh.get_repo(args.repo)
    pr = repo.get_pull(args.pr)

    posted, skipped, summary_url = post_comments(repo, pr, violations, args.sha)
    print(f"Summary: {summary_url}")
    print(f"Inline: {posted} posted, {skipped} skipped (existing)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
