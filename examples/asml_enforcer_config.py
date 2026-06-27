"""Example enforcer config for the agent-skill-management-library (ASML) repo.

ASML is a full-stack monorepo:
  backend/   — FastAPI + SQLAlchemy + Pydantic (Python)
  frontend/  — Angular standalone components (TypeScript + SCSS)
  web-e2e/   — Playwright E2E (TypeScript)
  scripts/   — bash + python dev/deploy automation
  infrastructure/ — Terraform

The CLAUDE.md files define conventions that agents must follow. This config
turns those conventions into pre-commit checks so violations never land.

Setup (one-time):
  cd /path/to/agent-skill-management-library
  enforcer install --force        # installs .git/hooks/pre-commit
  export ENFORCER_CONFIG=/path/to/asml_enforcer_config.py

Then every `git commit` runs the rules below against staged files.
"""

from enforcer import (
    Rule,
    Severity,
    LLMConsequence,
)
from enforcer.matchers import (
    RegexMatcher,
    LineCountMatcher,
    PathNotMatchingMatcher,
    AlwaysMatcher,
    ImportMatcher,
    FunctionComplexityMatcher,
    PairedFileMatcher,
)

WORKSPACE = "."

RULES = [
    # ─── Backend: no print() in app code (use structlog) ──────────────────
    Rule(
        id="backend-no-print",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*print\s*\(")],
        file_globs=["backend/app/**/*.py"],
        exclude_globs=[
            "backend/app/seeds/**/*",       # seed scripts may print
            "backend/app/scripts/**",      # CLI scripts may print
        ],
        message="print() found in app code. Use structlog for logging. ({file}:{line})",
        fix_instruction="Replace print() with structlog.get_logger().info()/error().",
    ),

    # ─── Backend: no bare except ─────────────────────────────────────────
    Rule(
        id="backend-no-bare-except",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"^\s*except\s*:")],
        file_globs=["backend/app/**/*.py"],
        message="Bare except: catches SystemExit/KeyboardInterrupt. Use except Exception. ({file}:{line})",
        fix_instruction="Change to `except Exception:` or a more specific exception.",
    ),

    # ─── Backend: no TODO/FIXME without owner ────────────────────────────
    # CLAUDE.md: comments should be non-obvious, not noise. TODOs without
    # an owner or issue link are noise.
    Rule(
        id="backend-todo-needs-owner",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"#\s*(TODO|FIXME|HACK|XXX)\b(?!\s*\(@)")],
        file_globs=["backend/app/**/*.py"],
        exclude_globs=["backend/app/seeds/**"],
        message="TODO/FIXME without owner at {file}:{line}. Use '# TODO(@name, #issue): …' or remove.",
        fix_instruction="Add owner reference or delete the TODO and address now.",
    ),

    # ─── Backend: API router files must not exceed 1000 lines ────────────
    # CLAUDE.md: per-kind registry keeps changes scoped. Giant router files
    # (artifacts.py is 6010 lines!) violate this spirit. Cap new files.
    Rule(
        id="backend-router-max-lines",
        severity=Severity.WARN,
        matchers=[LineCountMatcher(max_lines=1000)],
        file_globs=["backend/app/api/*.py"],
        message="Router file {file} has {matched_value} lines (max 1000). Split by domain.",
        fix_instruction="Extract sub-resources into separate router modules.",
    ),

    # ─── Backend: every endpoint file needs a paired integration test ────
    # CLAUDE.md: "Every new endpoint ships at least one integration test."
    Rule(
        id="backend-test-paired",
        severity=Severity.WARN,
        matchers=[PairedFileMatcher(
            source_glob="backend/app/api/*.py",
            derived_glob="backend/tests/integration/test_{stem}*.py",
            exclude_stems=["__init__", "router"],
        )],
        file_globs=["backend/app/api/*.py"],
        exclude_globs=["backend/app/api/__init__.py", "backend/app/api/router.py"],
        message="No integration test paired with {file}. CLAUDE.md requires tests for endpoints.",
        fix_instruction="Create backend/tests/integration/test_{stem}.py covering happy path + one failure mode.",
        diff_only=True,
    ),

    # ─── Backend: config drift guard ─────────────────────────────────────
    # CLAUDE.md: adding a config field requires syncing 6 places. Flag any
    # new field in *Config that isn't in .env.config.example.
    Rule(
        id="backend-config-drift",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"^\s+(\w+):\s+(str|int|bool|float)\b.*=\s*")],
        file_globs=["backend/app/config/*.py"],
        exclude_globs=["backend/app/config/__init__.py"],
        read_targets=[".env.config.example", ".env.secrets.example"],
        message="Config field in {file}:{line}. Verify it appears in .env.config.example and .env.secrets.example (see app/config/__init__.py checklist).",
        fix_instruction="Add the field to .env.config.example (non-secret) or .env.secrets.example (secret).",
        diff_only=True,
    ),

    # ─── Backend: API layer must not import from jobs layer ──────────────
    # ASML drift: artifacts.py imports app.jobs.broker, app.jobs.auto_approve
    Rule(
        id="backend-no-import-jobs",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"app\.jobs\."])],
        file_globs=["backend/app/api/**/*.py"],
        message="API layer imports from app.jobs at {file}:{line}. API should delegate to services, not jobs.",
        fix_instruction="Move the import to a service module, or inject the job via a service interface.",
        diff_only=True,
    ),

    # ─── Backend: services must not import from jobs layer ───────────────
    # ASML drift: artifact_publication.py imports app.jobs.quality
    Rule(
        id="backend-service-no-import-jobs",
        severity=Severity.ERROR,
        matchers=[ImportMatcher(forbidden_patterns=[r"app\.jobs\."])],
        file_globs=["backend/app/services/**/*.py"],
        message="Service layer imports from app.jobs at {file}:{line}. Services are lower than jobs — inverted dependency.",
        fix_instruction="Move the job logic into the service, or define an interface in services that jobs implement.",
        diff_only=True,
    ),

    # ─── Backend: no private symbol imports across modules ───────────────
    Rule(
        id="backend-no-private-imports",
        severity=Severity.WARN,
        matchers=[ImportMatcher(forbidden_patterns=[r"import\s+_\w+", r"from\s+\S+\s+import\s+_\w+"])],
        file_globs=["backend/app/**/*.py"],
        message="Private symbol (_-prefixed) imported across modules at {file}:{line}.",
        fix_instruction="Make the symbol public or move the logic to the importing module.",
        diff_only=True,
    ),

    # ─── Backend: functions must not exceed 75 lines ─────────────────────
    # ASML drift: _seed_default_bundles_for_kind (137 lines), _phrase (103 lines)
    Rule(
        id="backend-function-max-lines",
        severity=Severity.WARN,
        matchers=[FunctionComplexityMatcher(metric="lines", max_value=75)],
        file_globs=["backend/app/**/*.py"],
        exclude_globs=["backend/app/seeds/**", "backend/alembic/versions/**"],
        message="Function at {file}:{line} has {matched_value} lines (max 75). Split or extract.",
        fix_instruction="Extract sub-functions or move logic to a helper module.",
        diff_only=True,
    ),

    # ─── Backend: functions must not exceed 5 parameters ──────────────────
    # ASML drift: hybrid_search (16 params), register_repo_source (12 params)
    Rule(
        id="backend-function-max-params",
        severity=Severity.WARN,
        matchers=[FunctionComplexityMatcher(metric="params", max_value=5)],
        file_globs=["backend/app/**/*.py"],
        exclude_globs=["backend/app/seeds/**", "backend/tests/**"],
        message="Function at {file}:{line} has {matched_value} parameters (max 5). Group into a dataclass.",
        fix_instruction="Group related parameters into a dataclass/Pydantic model and pass as single arg.",
        diff_only=True,
    ),

    # ─── Frontend: no console.log in app code ────────────────────────────
    Rule(
        id="frontend-no-console-log",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"console\.(log|debug|info)\s*\(")],
        file_globs=["frontend/src/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts", "frontend/src/main.ts"],
        message="console.{matched_value} found. Remove debug logging before commit. ({file}:{line})",
        fix_instruction="Delete the console.* call or move to a proper logging service.",
    ),

    # ─── Frontend: no raw hex colors — use Material theme ────────────────
    Rule(
        id="frontend-no-raw-hex",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
        file_globs=["frontend/src/**/*.ts", "frontend/src/**/*.scss"],
        exclude_globs=[
            "frontend/src/**/*.spec.ts",
            "frontend/src/styles/material-theme.scss",
        ],
        read_targets=["frontend/src/styles/material-theme.scss"],
        message="Raw hex color '{matched_value}' at {file}:{line}. Use Material theme tokens or var(--color-*).",
        fix_instruction="Replace hex with mat.$color-token or var(--color-*) from material-theme.scss.",
    ),

    # ─── Frontend: standalone components must use OnPush ────────────────
    # CLAUDE.md convention: all new Angular components are standalone + OnPush.
    # This is an LLM consequence rule — the regex catches the pattern, the LLM
    # reviews whether OnPush is correctly applied (not just present but
    # actually used with signals/computed).
    Rule(
        id="frontend-component-onpush",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"@Component\s*\(")],
        file_globs=["frontend/src/app/components/**/*.ts", "frontend/src/pages/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts"],
        message="Angular component at {file}:{line}. Verify standalone: true and ChangeDetectionStrategy.OnPush.",
        fix_instruction="Add standalone: true and changeDetection: ChangeDetectionStrategy.OnPush.",
        llm_consequence=LLMConsequence(
            provider="default",
            model="gpt-4",
            prompt=(
                "Review this Angular component. Does it use standalone: true and "
                "ChangeDetectionStrategy.OnPush? Are inputs signals (input()) "
                "or @Input()? Flag any component using legacy @Input/@Output "
                "or missing OnPush. Be concise."
            ),
        ),
    ),

    # ─── Frontend: every component needs a paired .spec.ts ───────────────
    # CLAUDE.md: "Every new component or service ships at least one unit test."
    Rule(
        id="frontend-test-paired",
        severity=Severity.WARN,
        matchers=[PairedFileMatcher(
            source_glob="frontend/src/app/components/**/*.ts",
            derived_glob="frontend/src/app/components/{dir}/{stem}.spec.ts",
        )],
        file_globs=["frontend/src/app/components/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts", "frontend/src/**/*.d.ts"],
        message="No .spec.ts paired with {file}. CLAUDE.md requires Vitest unit tests.",
        fix_instruction="Create {stem}.spec.ts alongside the file covering visible behaviour.",
        diff_only=True,
    ),

    # ─── Frontend: every service needs a paired .spec.ts ────────────────
    Rule(
        id="frontend-service-test-paired",
        severity=Severity.WARN,
        matchers=[PairedFileMatcher(
            source_glob="frontend/src/app/services/**/*.ts",
            derived_glob="frontend/src/app/services/{stem}.spec.ts",
        )],
        file_globs=["frontend/src/app/services/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts", "frontend/src/**/*.d.ts"],
        message="No .spec.ts paired with {file}. CLAUDE.md requires Vitest unit tests.",
        fix_instruction="Create {stem}.spec.ts alongside the file covering public methods.",
        diff_only=True,
    ),

    # ─── Frontend: every page needs a paired .spec.ts ────────────────────
    Rule(
        id="frontend-page-test-paired",
        severity=Severity.WARN,
        matchers=[PairedFileMatcher(
            source_glob="frontend/src/pages/**/*.ts",
            derived_glob="frontend/src/pages/{dir}/{stem}.spec.ts",
        )],
        file_globs=["frontend/src/pages/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts", "frontend/src/**/*.d.ts"],
        message="No .spec.ts paired with {file}. CLAUDE.md requires Vitest unit tests.",
        fix_instruction="Create {stem}.spec.ts alongside the file covering visible behaviour.",
        diff_only=True,
    ),

    # ─── Frontend: use 'artifact' not 'skill' in new code ────────────────
    # CLAUDE.md: "Use 'artifact' when writing new code or docs. 'skill' survives
    # only as ArtifactKind.skill enum value and test-fixture strings."
    Rule(
        id="frontend-artifact-vocabulary",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"\bclass\s+\w*Skill\w*|\bSkillService\b|\bSkillCard\b|\bSkillDetail\b")],
        file_globs=["frontend/src/**/*.ts"],
        exclude_globs=["frontend/src/**/*.spec.ts", "frontend/src/api/generated/**"],
        message="Legacy 'Skill' naming at {file}:{line}. Use 'Artifact' per CLAUDE.md vocabulary.",
        fix_instruction="Rename Skill* → Artifact* (class, selector, service). Only ArtifactKind.skill enum keeps 'skill'.",
    ),

    # ─── Screenshots: no .png in repo root ───────────────────────────────
    # CLAUDE.md: "Always save screenshots into .playwright-mcp/ (gitignored)."
    Rule(
        id="no-root-screenshots",
        severity=Severity.ERROR,
        matchers=[PathNotMatchingMatcher(pattern=".playwright-mcp/**")],
        file_globs=["*.png", "*.jpg", "*.jpeg", "*.webp"],
        exclude_globs=[".playwright-mcp/**", "docs/**", "frontend/src/assets/**"],
        message="Screenshot {file} in repo root. Move to .playwright-mcp/ (gitignored).",
        fix_instruction="Move file to .playwright-mcp/ or add to docs/assets/ if committed.",
    ),

    # ─── Branch guard: never commit to main ─────────────────────────────
    # CLAUDE.md: "Never develop directly on main." Pre-commit can't check
    # branch directly, but it can block edits to main-tracked files.
    # This is an LLM rule — fires on every staged file, LLM checks if the
    # branch is main (it can't, but the warning serves as a reminder).
    # Better: enforced by the hook script itself. Left as documentation here.
    # Rule(
    #     id="no-main-commits",
    #     severity=Severity.ERROR,
    #     matchers=[AlwaysMatcher(matched_value="main-branch-check")],
    #     file_globs=["**/*"],
    #     message="Committing to main is not allowed. Create a feature branch first.",
    #     fix_instruction="git checkout -b <type>/<slug> before committing.",
    # ),

    # ─── General: no secrets in code ─────────────────────────────────────
    Rule(
        id="no-hardcoded-secrets",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]")],
        file_globs=["**/*.py", "**/*.ts", "**/*.tsx"],
        exclude_globs=["**/*.spec.ts", "**/*test*", "**/seeds/**", "**/.env*"],
        message="Possible hardcoded secret at {file}:{line}. Use env var / Secrets Manager.",
        fix_instruction="Move to .env.secrets (local) or AWS Secrets Manager (cluster). See app/config/__init__.py.",
    ),

    # ─── General: no .env files committed (except .example) ─────────────
    Rule(
        id="no-env-files",
        severity=Severity.ERROR,
        matchers=[RegexMatcher(r".*")],  # match any .env file
        file_globs=[".env", ".env.config", ".env.secrets", ".env.secrets.dev", ".env.secrets.prod"],
        exclude_globs=[".env.config.example", ".env.secrets.example", ".env.secrets.dev.example", ".env.secrets.prod.example"],
        message="Gitignored env file {file} is being committed. Remove from staging.",
        fix_instruction="git reset HEAD {file} — env files are gitignored.",
    ),

    # ─── Backend: Alembic migration long-running flag ────────────────────
    # CLAUDE.md: long-running migrations must set LONG_RUNNING = True.
    # Flag any migration that adds an index without CONCURRENTLY.
    Rule(
        id="backend-migration-index-check",
        severity=Severity.WARN,
        matchers=[RegexMatcher(r"create_index\s*\(")],
        file_globs=["backend/alembic/versions/*.py"],
        message="Migration at {file}:{line} creates an index. If large table, use CONCURRENTLY + set LONG_RUNNING = True. See backend/CLAUDE.md.",
        fix_instruction="Set LONG_RUNNING: bool = True on the migration class, or use op.execute('CREATE INDEX CONCURRENTLY …').",
    ),
]

SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}

LLM_CONFIG = {
    "concurrency": 3,
    "timeout": 45,
}
