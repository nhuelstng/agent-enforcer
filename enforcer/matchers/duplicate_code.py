"""DuplicateCodeMatcher: token-based n-gram similarity detection across files."""
from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from enforcer.types import Match, FileContext, Needs

# ponytail: token regex — identifiers, numbers, strings, operators. Strips whitespace/comments.
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+|'[^\']*'|\"[^\"]*\"|==|!=|<=|>=|[-+*/%=<>!&|^~?:;.(){}\[\],]")


_COMMENT_RE = re.compile(r"#.*$", re.MULTILINE)


def _tokenize(source: str) -> list[str]:
    source = _COMMENT_RE.sub("", source)
    return _TOKEN_RE.findall(source)


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@dataclass
class DuplicateCodeMatcher:
    """Detects duplicate code blocks across files via token n-gram overlap.
    Uses shared_ctx to accumulate tokens per file. First pass collects n-grams,
    second pass emits matches for files sharing above-threshold overlap.

    Config author sets min_tokens (block size) and min_overlap (fraction 0-1).
    The matcher needs two phases: collect (run on each file) + report (run once
    after all files processed). The runner calls find() per-file; shared_ctx
    stores the n-gram index. Call finalize_duplicates(shared_ctx) after all files
    to get cross-file matches."""
    min_tokens: int = 10
    min_overlap: float = 0.8
    workspace: str = "."
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx if shared_ctx is not None else {}
        if not file_ctx.raw:
            return []

        key = "_dup_index"
        if key not in shared_ctx:
            shared_ctx[key] = {"ngrams": defaultdict(set), "files": {}}

        idx = shared_ctx[key]
        tokens = _tokenize(file_ctx.raw)
        ngrams = _ngrams(tokens, self.min_tokens)

        idx["files"][file_ctx.path] = ngrams
        for gram in ngrams:
            idx["ngrams"][gram].add(file_ctx.path)

        return []

    def finalize_duplicates(self, shared_ctx: dict) -> list[Match]:
        """Call after all files processed. Returns matches for duplicate blocks."""
        idx = shared_ctx.get("_dup_index")
        if not idx:
            return []

        matches: list[Match] = []
        files = idx["files"]
        paths = sorted(files.keys())

        for i, path_a in enumerate(paths):
            grams_a = files[path_a]
            if not grams_a:
                continue
            for path_b in paths[i + 1 :]:
                grams_b = files[path_b]
                if not grams_b:
                    continue
                overlap = grams_a & grams_b
                if not overlap:
                    continue
                ratio = len(overlap) / min(len(grams_a), len(grams_b))
                if ratio >= self.min_overlap:
                    matches.append(Match(
                        file=path_a,
                        line=0,
                        matched_value=f"{path_b} ({ratio:.0%} overlap, {len(overlap)} blocks)",
                    ))
                    matches.append(Match(
                        file=path_b,
                        line=0,
                        matched_value=f"{path_a} ({ratio:.0%} overlap, {len(overlap)} blocks)",
                    ))
        return matches
