"""DuplicateCodeMatcher: token-based n-gram similarity detection across files."""
from __future__ import annotations
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from pathlib import Path
from enforcer.types import Match, FileContext, Needs

# ponytail: token regex — identifiers, numbers, strings, operators. Strips whitespace.
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+|'[^\']*'|\"[^\"]*\"|==|!=|<=|>=|[-+*/%=<>!&|^~?:;.(){}\[\],]")
# ponytail: Python comments only — TS/JS/Go comments not stripped. Acceptable: config author gates via file_globs.
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
    Uses shared_ctx to accumulate tokens per file. Two-phase: find() collects
    n-grams per file, finalize_duplicates() emits matches for file pairs sharing
    above-threshold overlap.

    Uses overlap coefficient (overlap / min(len_a, len_b)) — correct for
    subset/containment detection. Jaccard would penalize small files fully
    contained in large ones.

    Memory: n-grams hashed to ints to reduce footprint. Inverted index used
    for O(K) candidate pair generation instead of O(n²) pairwise scan."""
    min_tokens: int = 10
    min_overlap: float = 0.8
    workspace: str = "."
    needs: Needs = Needs.RAW

    def __post_init__(self):
        # ponytail: key by instance config — prevents collision between multiple DuplicateCodeMatcher instances
        self._ctx_key = f"_dup_index_{self.min_tokens}_{self.min_overlap}"

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx if shared_ctx is not None else {}
        if not file_ctx.raw:
            return []

        key = self._ctx_key
        if key not in shared_ctx:
            shared_ctx[key] = {
                "files": {},            # path -> set of n-gram hashes
                "ngram_files": defaultdict(set),  # n-gram hash -> set of paths (inverted index)
                "file_lines": {},       # path -> {n-gram hash -> first line number}
                "finalized": False,
            }

        idx = shared_ctx[key]
        if file_ctx.path in idx["files"]:
            return []

        tokens = _tokenize(file_ctx.raw)
        ngrams = _ngrams(tokens, self.min_tokens)

        # ponytail: hash n-grams to ints — ~28x smaller than storing tuples of strings
        gram_hashes = set()
        gram_lines = {}
        lines = file_ctx.raw.splitlines()
        for gram in ngrams:
            gh = hash(gram)
            gram_hashes.add(gh)
            idx["ngram_files"][gh].add(file_ctx.path)
            if gh not in gram_lines:
                # find first line where this n-gram starts
                gram_lines[gh] = self._find_line(lines, gram)

        idx["files"][file_ctx.path] = gram_hashes
        idx["file_lines"][file_ctx.path] = gram_lines

        return []

    def _find_line(self, lines: list[str], gram: tuple[str, ...]) -> int:
        """Find the first line number where an n-gram appears."""
        for i, line in enumerate(lines):
            if gram[0] in line:
                return i + 1
        return 1

    def finalize_duplicates(self, shared_ctx: dict) -> list[Match]:
        """Call after all files processed. Returns matches for duplicate blocks.
        Uses inverted index for O(K) candidate pair generation where K = actual shared pairs."""
        idx = shared_ctx.get(self._ctx_key)
        if not idx or idx.get("finalized"):
            return []

        idx["finalized"] = True
        matches: list[Match] = []

        # ponytail: use inverted index to find candidate pairs — O(total_grams) not O(n²)
        pair_overlaps: Counter = Counter()
        for gram_hash, paths in idx["ngram_files"].items():
            if len(paths) < 2:
                continue
            path_list = sorted(paths)
            for i in range(len(path_list)):
                for j in range(i + 1, len(path_list)):
                    pair_overlaps[(path_list[i], path_list[j])] += 1

        files = idx["files"]
        file_lines = idx["file_lines"]
        for (path_a, path_b), overlap_count in pair_overlaps.items():
            grams_a = files.get(path_a, set())
            grams_b = files.get(path_b, set())
            if not grams_a or not grams_b:
                continue
            ratio = overlap_count / min(len(grams_a), len(grams_b))
            if ratio >= self.min_overlap:
                line_a = self._first_overlap_line(file_lines.get(path_a, {}), files.get(path_b, set()))
                line_b = self._first_overlap_line(file_lines.get(path_b, {}), files.get(path_a, set()))
                matches.append(Match(
                    file=path_a,
                    line=line_a,
                    matched_value=f"{path_b} ({ratio:.0%} overlap, {overlap_count} blocks)",
                ))
                matches.append(Match(
                    file=path_b,
                    line=line_b,
                    matched_value=f"{path_a} ({ratio:.0%} overlap, {overlap_count} blocks)",
                ))
        return matches

    def _first_overlap_line(self, gram_lines: dict, other_grams: set) -> int:
        """Find the first line of the first n-gram shared with the other file."""
        for gh, line in gram_lines.items():
            if gh in other_grams:
                return line
        return 1
