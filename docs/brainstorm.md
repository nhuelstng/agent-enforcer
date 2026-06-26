# Pre-Commit Agent Enforcer — Brainstorm Notes

## Problem

Coding agents are unreliable at following conventions. They forget to use CSS
variables, hardcode hex values, define constants in the wrong place, introduce
design drift. Conventions often exist only as comments — zero enforcement.

**Real example found in `agent-skill-management-library`:**

`frontend/src/styles/colors.scss:1-2` says:

> All component stylesheets MUST use var(--color-*) / var(--font-*); no raw hex.

But `artifact-kind-header.component.ts:144-184` has ~20 hardcoded hex values.
`artifact-card-with-image.component.ts` has raw `rgba()` calls. The convention
is a comment. The drift is real. No tool catches it.

## Goal

Deterministically find deviations from conventions and prevent an agent from
committing them without fixing. Output ALL issues at once (no back-and-forth)
with configurable instructions for the agent on what to do about them.

---

## Decisions (locked)

| Decision | Choice | Reason |
|----------|--------|--------|
| Tool relationship | Standalone CLI + MCP server, pre-commit hook as thin wrapper | Pre-commit framework's per-file hook model can't do cross-file analysis or aggregate output |
| Config model | Convention as code (Python rules) | Full flexibility; dev writes rule once, agents forced to comply |
| Rule scope | CSS vars/classes, JS/TS constants, import paths, file location, naming conventions, design tokens, generic AST/text | Generic API so any convention can be expressed |
| Output format | JSON or text (switchable via `--format`) | `--format json` for agents, `--format text` for humans. Default: text. Output printed to stdout on every run so agent reads it directly from pre-commit output |
| Language | Python | Matches pre-commit ecosystem; good AST tooling |
| Agent integration | Hook (hard gate) + MCP (interactive self-check) | Hook catches what agent missed; MCP lets agent self-check before committing |
| Severity | Configurable severity mapping | Rules return severity; config maps to actions (error=block, warn=print, info=hint) |
| Rule discovery | Config-registered | Explicit enable/disable, ordering, per-rule config |
| Check scope | Staged default, `--all` flag | Fast pre-commit; whole-repo for CI |
| Fix instructions | Text instruction only | Keeps it simple; agent reads hint and figures out fix |
| Cross-file context | Shared context (read targets) | Rules declare read targets (e.g. colors.scss); tool builds context, passes to rules |
| Config format | Python file (config as code) | Matches "convention as code" philosophy; can reference rule classes directly |

---

## Approaches Considered

### Approach A: Pure pre-commit framework hook (extend, don't wrap)

Tool is a single Python package registered in `.pre-commit-config.yaml` as a
local hook. Runs per-staged-file.

**Pros:**
- Zero new infra
- Fits existing workflow
- Devs already know it

**Cons:**
- **Kills cross-file analysis.** Can't enforce "only use variables defined in
  colors.scss" — the hook checking `x.component.ts` has no idea what's in
  `colors.scss` unless it parses colors.scss itself on every invocation.
- Can't aggregate all issues into one JSON blob. Pre-commit runs hooks
  per-file; a multi-file rule can't report all 50 violations at once.
- The "list ALL issues at once" goal breaks.

**Verdict: doesn't meet requirements.** The shared-context model is
incompatible with pre-commit's per-file hook model.

---

### Approach B: Standalone CLI + MCP server (recommended) — CHOSEN

A standalone Python tool (`enforcer`) with two front-ends:

1. **CLI** — `enforcer check [paths]` → output printed to stdout. `--format json`
   for agent consumption, `--format text` for humans. Default: text. Runs as a
   pre-commit hook via a thin local hook entry that calls
   `enforcer check --staged --format json`. Non-zero exit blocks commit. Output
   is always printed directly so the agent reads it from pre-commit output.
2. **MCP server** — `enforcer mcp` exposes a `check_conventions` tool. Agent
   calls it before committing to self-check. Returns same JSON.

The tool owns its config (`enforcer_config.py`), its rule runner, its context
builder. Pre-commit framework is just a trigger — the local hook is 3 lines
that shell out to `enforcer check`.

**Pros:**
- Full control over output format (single JSON blob with ALL issues)
- Cross-file context works (tool parses read-target files first, builds
  context, then runs rules against staged files with that context)
- MCP server gives agent proactive self-check ability
- Config-as-code fits naturally
- Can run `--all` for whole-repo CI checks
- Configurable severity mapping

**Cons:**
- New tool to maintain
- Not "just another pre-commit hook" — separate binary with own config
- Slightly more setup (install tool + register hook)

**Mitigation:**
- Ship as pip-installable package
- Hook config is 5 lines in `.pre-commit-config.yaml`

---

### Approach C: Wrap pre-commit framework with orchestration layer

A wrapper that sits above pre-commit. Reads its own config, runs all rules,
collects results, then calls pre-commit's hooks as a second pass.

**Pros:**
- Keeps existing hooks
- Unified output

**Cons:**
- **Complexity for no gain.** Reimplements pre-commit's file-staging logic, then
  runs own rules, then shells out to pre-commit.
- Two config files (yours + `.pre-commit-config.yaml`)
- Duplicates file filtering, staging, re-staging fixed files
- Maintenance burden

**Verdict: over-engineered.** The thing you want (custom rules + cross-file
context + JSON output) is orthogonal to what pre-commit does (run N independent
hooks on staged files). Don't wrap — coexist.

---

## Recommendation: Approach B

Only approach that satisfies all requirements:

- Cross-file context (read targets parsed before rules run)
- Single JSON output with ALL issues
- Config-as-code (Python config file)
- Hard gate (pre-commit hook shells out to CLI)
- Agent self-check (MCP server)
- `--all` flag for whole-repo CI
- Configurable severity mapping (error blocks, warn prints, info hints)

The pre-commit framework stays for what it's good at (ruff, eslint, trailing
whitespace). This tool handles what it can't: cross-file convention enforcement
with structured output.
