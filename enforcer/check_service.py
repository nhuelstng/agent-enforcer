"""check_service: the one orchestration ring shared by the CLI and the MCP server.

Each entry point only translates its own arguments in and formats matches out; the
sequence that used to be copy-pasted in both — narrow the rule set, collect files, apply
.enforcerignore, render the conventions doc from the *full* rule set, build the runner and
builder, run the shared pass — lives here once, so the two paths cannot drift (the reason
test_mcp_parity existed). verify-fix routes through the same runner primitive rather than
re-gluing a third mini-pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass
from enforcer.types import Severity, Match
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.ignore import load_enforcerignore, is_ignored
from enforcer.check_runner import collect_files, build_shared_ctx, run_check_pass, CheckOptions


@dataclass
class CheckRequest:
    """What to check and how — the run knobs both entry points share, minus output format.

    Bundling them keeps run_check's interface small and gives the CLI and MCP one value to
    build instead of a long positional call they can drift on."""
    staged: bool = False
    all_files: bool = False
    paths: tuple = ()
    base_ref: str | None = None
    no_llm: bool = False
    min_severity: Severity = Severity.INFO
    rule_id: str | None = None
    workspace: str | None = None


def run_check(config, request: CheckRequest) -> list[Match]:
    """Run the full check ring for a request and return the aggregated matches.

    The conventions doc is rendered from the complete rule set captured before --rule-id
    narrows the run, so a single-rule run never spuriously trips the doc-staleness rule.
    .enforcerignore is applied in every mode except staged. Mutates config.rules when
    request.rule_id narrows the run (the caller's own config object)."""
    all_rules = list(config.rules)
    if request.rule_id:
        config.rules = [r for r in config.rules if r.id == request.rule_id]
    ws = request.workspace or config.workspace

    file_list, status_map = collect_files(
        request.staged, request.all_files, request.paths, ws, base_ref=request.base_ref)
    ignore_patterns = load_enforcerignore(ws) if not request.staged else []
    if ignore_patterns:
        file_list = [f for f in file_list if not is_ignored(f, ignore_patterns)]

    runner = RuleRunner(config.rules, workspace=ws, no_llm=request.no_llm,
                        min_severity=request.min_severity, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)
    from enforcer.docs import render_rules_doc
    rendered_doc = render_rules_doc(all_rules, workspace=config.workspace or ws)

    return run_check_pass(runner, builder, config, file_list, CheckOptions(
        status_map=status_map, staged=request.staged, diff_ref=request.base_ref,
        rendered_doc=rendered_doc, no_llm=request.no_llm, all_files=request.all_files,
    ))


def verify_fix_matches(config, path: str, rule_id: str, no_llm: bool = False) -> "list[Match] | None":
    """Re-check one rule on one file (full-file scan). Returns matches, or None for an
    unknown rule id.

    Routes the check through RuleRunner.check_rule so the file-glob gate, predicates, and
    LLM-consequence handling are the runner's — not a hand-rolled copy reaching into its
    internals. Every line is marked changed so diff_only rules fire on the re-checked file."""
    rule = next((r for r in config.rules if r.id == rule_id), None)
    if rule is None:
        return None
    ws = config.workspace
    runner = RuleRunner(config.rules, workspace=ws, no_llm=no_llm, llm_config=config.llm_config)
    builder = FileContextBuilder(config.rules, workspace=ws)
    from enforcer.docs import render_rules_doc
    rendered_doc = render_rules_doc(config.rules, workspace=config.workspace or ws)
    shared_ctx = build_shared_ctx(config, builder, ws,
                                  staged_files=[path] if path else None, rendered_doc=rendered_doc)
    shared_ctx.llm_enabled = runner.llm_executor.enabled
    shared_ctx.llm_config = runner.llm_config

    ctx = builder.build(path)
    if ctx.raw is not None:
        ctx.changed_lines = set(range(1, ctx.raw.count("\n") + 2))
    return runner.check_rule(rule, ctx, shared_ctx)
