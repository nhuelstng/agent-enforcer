"""Env-file <-> Terraform block key sync. Replaces the 80-line
EnvTerraformSyncMatcher in example-repo's enforcer_config.py.

Copy this into your enforcer_config.py, adjust the paths and exclude_keys to
match your project, and the two rules enforce env<->TF key consistency.
"""
from enforcer import Rule, Severity
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys

TF_FILES = "infrastructure/aws/service/*/main.tf"

# Keys present in .env.config.example that are intentionally absent from
# Terraform app_environment because they are dev-only or have universal
# code defaults that make cluster injection unnecessary.
CONFIG_DEV_LOCAL_KEYS = {
    "ANTHROPIC_BASE_URL",
    "LLM_DEBUG_PROMPTS",
    "AUTO_APPROVE_DEFAULT_THRESHOLD",
    "AUTO_APPROVE_DEFAULT_COOLDOWN_MINUTES",
    "MCP_OAUTH_ENABLED",
    "DEV__AUTH__ADMIN_URL",
    "DEV__AUTH__ADMIN_REALM",
    "DEV__AUTH__ADMIN_USER",
    "DEV__AUTH__TARGET_REALM",
}

# Keys present in .env.secrets.example that are intentionally absent from
# Terraform app_secrets (dev-local credentials never pushed to clusters).
SECRETS_DEV_LOCAL_KEYS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEV__AUTH__ADMIN_PASSWORD",
}

RULES = [
    Rule(
        id="env-config-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[TF_FILES],
            exclude_keys=CONFIG_DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.config.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.config.example but missing from app_environment in Terraform.",
        fix_instruction=(
            "Add the key to infrastructure/aws/service/dev/main.tf and "
            "infrastructure/aws/service/prod/main.tf app_environment blocks. "
            "If it is intentionally dev-local, add it to CONFIG_DEV_LOCAL_KEYS."
        ),
        rationale=(
            "Every non-sensitive config key in .env.config.example must appear in "
            "Terraform app_environment. Agents update the env file for local dev "
            "but forget Terraform — the cluster then fails on the next deploy."
        ),
    ),
    Rule(
        id="env-secrets-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_secrets"),
            target_globs=[TF_FILES],
            exclude_keys=SECRETS_DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.secrets.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.secrets.example but missing from app_secrets in Terraform.",
        fix_instruction=(
            "Add the key to infrastructure/aws/service/dev/main.tf and "
            "infrastructure/aws/service/prod/main.tf app_secrets blocks. "
            "If it is intentionally dev-local, add it to SECRETS_DEV_LOCAL_KEYS."
        ),
        rationale=(
            "Every cluster-facing secret in .env.secrets.example must appear in "
            "Terraform app_secrets. Agents populate the env file for local dev "
            "but forget Terraform — the deployed service starts without the credential."
        ),
    ),
]

WORKSPACE = "."
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
