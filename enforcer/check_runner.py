"""Shared check pipeline: file collection, context building, rule execution. Used by cli.py and mcp_server.py."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from enforcer.check_context import CheckContext
from enforcer.git import Git, parse_name_status as _parse_name_status

_JUNK_DIRS = {".git", ".worktrees", "node_modules", "__pycache__", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
               "*.egg-info"}


def _glob_any_match(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _needs_import_graph(rules: list) -> bool:
    """Return True if any rule's matcher tree contains an import-graph consumer.

    Import-graph consumers (ArchitectureMatcher, DeepImportBarrierMatcher) satisfy the
    ImportGraphConsumer Protocol; check_runner builds __import_graph__ only when one is
    present, keeping the graph pass off the hot path for graph-free configs.
    """
    from enforcer.types import ImportGraphConsumer
    from enforcer.matcher_tree import iter_matchers
    all_matchers = [m for rule in rules for m in rule.matchers]
    return any(
        isinstance(m, ImportGraphConsumer) and m.reads_import_graph
        for m in iter_matchers(all_matchers)
    )


def _parse_diff_changed_lines(repo_root: str, file_path: str, ref: str | None = None) -> set[int] | None:
    """Return the changed (added) line numbers for a file, or None when no diff is available.

    ref=None uses --cached (staged); ref set uses <ref>...HEAD. Thin caller over the git
    seam, kept so the scan-mode dispatch in _ctx_for_file has one patchable indirection."""
    return Git(repo_root).changed_lines(file_path, ref=ref)


def build_change_context(ws: str, status_map: dict[str, str]) -> "ChangeContext":
    """Build ChangeContext from git metadata + status_map. Reads commit subject + branch."""
    from enforcer.types import ChangeContext

    git = Git(ws)
    subject = git.commit_subject()
    commit_msg = "" if (subject is None or subject.startswith("Merge")) else subject
    branch = git.current_branch()

    created = [f for f, s in status_map.items() if s == "added"]
    modified = [f for f, s in status_map.items() if s == "modified"]
    deleted = [f for f, s in status_map.items() if s == "deleted"]
    renamed = [f for f, s in status_map.items() if s == "renamed"]

    return ChangeContext(
        commit_msg=commit_msg,
        branch=branch,
        created=created,
        modified=modified,
        deleted=deleted,
        renamed=renamed,
    )


def collect_files(staged: bool, all_files: bool, paths: tuple, ws: str, base_ref: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Collect the list of files to check based on CLI mode. Returns (file_list, status_map)."""
    if staged:
        return Git(ws).changed_files(staged=True)
    if base_ref:
        return Git(ws).changed_files(ref=base_ref)
    if all_files:
        return _walk_repo_files(ws), {}
    return list(paths), {}


def _walk_repo_files(ws: str) -> list[str]:
    """Return every repo-relative file under ws, skipping junk dirs (.git, build, .worktrees, ...)."""
    file_list: list[str] = []
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if not _glob_any_match(d, _JUNK_DIRS)]
        file_list.extend(os.path.relpath(os.path.join(root, f), ws) for f in files)
    return file_list


def _load_read_targets(rules: list, builder, ws: str, shared_ctx: dict) -> None:
    """Cache a FileContext for every path matched by any rule's read_targets globs."""
    root = Path(ws)
    targets = {t for rule in rules for t in getattr(rule, "read_targets", [])}
    for target in targets:
        _cache_glob_matches(root, ws, target, builder, shared_ctx)


def _cache_glob_matches(root: Path, ws: str, target: str, builder, shared_ctx: dict) -> None:
    """Build and cache a FileContext for each path matching one read_target glob."""
    for match in root.glob(target):
        rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
        if rel not in shared_ctx:
            shared_ctx[rel] = builder.build(rel)


def build_shared_ctx(config, builder, ws: str, staged_files: list[str] | None = None,
                     rendered_doc: str | None = None) -> CheckContext:
    """Build the CheckContext from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx = CheckContext(
        rules=config.rules,
        workspace=config.workspace or ws,
        rendered_doc=rendered_doc or "",
    )
    _load_read_targets(config.rules, builder, ws, shared_ctx)
    if staged_files and _needs_import_graph(config.rules):
        from enforcer.import_graph import ImportGraphBuilder
        graph_builder = ImportGraphBuilder(
            builder=builder, workspace=ws,
            source_roots=getattr(config, "source_roots", None),
        )
        # {source: {target: import_line}} recorded at resolution time, so a
        # matcher attributes an edge to the exact import that produced it.
        shared_ctx.set_import_graph(graph_builder.build(staged_files), graph_builder.import_lines)
    return shared_ctx


@dataclass
class CheckOptions:
    """How to run a check pass: file statuses, mode flags, and the pre-rendered doc.

    Bundles the per-invocation knobs so run_check_pass keeps a small interface and the
    CLI/MCP entry points pass one value object instead of a long positional list.
    rendered_doc is supplied by the caller because rendering lives in the io layer."""
    status_map: dict[str, str] = field(default_factory=dict)
    staged: bool = False
    diff_ref: str | None = None
    rendered_doc: str = ""
    no_llm: bool = False
    # ponytail: full-repo scan. Every line counts as in-scope, so diff_only rules
    # fire on the whole file (a full audit has no diff to gate against).
    all_files: bool = False


def run_check_pass(runner, builder, config, file_list: list[str], options: "CheckOptions") -> list:
    """Run one full check pass and return the aggregated matches.

    The single entry point both the CLI and the MCP server go through: it assembles
    the shared context (read-targets, import graph, rendered conventions doc, change
    metadata, LLM flags), then runs the three rule phases — per-file CONTENT rules,
    METADATA rules, and cross-file finalizers. Callers stay thin: they build the
    runner/builder, collect files, and format output; the pipeline lives here so the
    two entry points cannot drift. The workspace is taken from the runner.
    """
    ws = runner.workspace
    shared_ctx = build_shared_ctx(config, builder, ws, staged_files=file_list, rendered_doc=options.rendered_doc)
    shared_ctx.change = build_change_context(ws, options.status_map)
    # LLM state has one source of truth — the runner's executor — so the CLI and MCP
    # paths cannot compute "enabled" one way here and another way in the runner.
    shared_ctx.llm_enabled = runner.llm_executor.enabled
    shared_ctx.llm_config = runner.llm_config
    # ponytail: full-scan flag read by run_cross_file_finalizers so diff_only
    # finalizer rules also run under --all.
    shared_ctx.all_files = options.all_files

    all_matches = run_checks(runner, builder, file_list, shared_ctx, options)
    all_matches.extend(runner.run_metadata_rules(shared_ctx))
    all_matches.extend(runner.run_cross_file_finalizers(shared_ctx))
    return all_matches


def _all_line_numbers(ctx) -> set[int] | None:
    """Return every 1-based line number of a file, or None when its text is unavailable.

    A full scan marks the whole file as in-scope so diff_only rules fire on every line
    (there is no diff to gate against); an unreadable file stays None and is skipped."""
    if ctx.raw is None:
        return None
    return set(range(1, ctx.raw.count("\n") + 2))


def _ctx_for_file(builder, path: str, ws: str, options: "CheckOptions"):
    """Build a file's context with changed_lines set per the scan mode.

    diff_ref → lines changed vs the ref; staged → lines changed in the index;
    all_files → every line (full audit); otherwise the plain file (diff_only rules
    are suppressed). Each branch is a guard clause so the modes stay flat and explicit."""
    import dataclasses
    ctx = builder.build(path)
    status = options.status_map.get(path, "modified")
    if options.diff_ref is not None:
        return dataclasses.replace(ctx, status=status,
                                   changed_lines=_parse_diff_changed_lines(ws, path, ref=options.diff_ref))
    if options.staged:
        return dataclasses.replace(ctx, status=status,
                                   changed_lines=_parse_diff_changed_lines(ws, path))
    if options.all_files:
        return dataclasses.replace(ctx, status=status, changed_lines=_all_line_numbers(ctx))
    if status != "modified":
        return dataclasses.replace(ctx, status=status)
    return ctx


def run_checks(runner, builder, file_list: list[str], shared_ctx: dict, options: "CheckOptions") -> list:
    """Run per-file rules across file_list and return aggregated matches.

    Scan mode (diff/staged/all) comes from options; the workspace from the runner."""
    from enforcer.types import Match
    ws = runner.workspace
    all_matches: list[Match] = []
    for f in file_list:
        if not f:
            continue
        all_matches.extend(runner.run_rules_for_file(_ctx_for_file(builder, f, ws, options), shared_ctx))
    return all_matches
