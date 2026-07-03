"""Env-file <-> Terraform block key sync.

Copy this into your enforcer_config.py, adjust the paths and exclude_keys to
match your project, and the two rules enforce env<->TF key consistency.

Drops keys present in .env.example but missing from the corresponding
Terraform variable block, and vice versa.
"""
from enforcer import Rule, Severity
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys

TF_FILES = "infrastructure/*/main.tf"

# Keys in .env.example intentionally absent from Terraform (dev-only or
# code-defaulted). Add yours here.
DEV_LOCAL_KEYS = {
    "LOG_LEVEL",
    "DEBUG",
}

RULES = [
    Rule(
        id="env-tf-config-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[TF_FILES],
            exclude_keys=DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is in .env.example but missing from app_environment in Terraform.",
        fix_instruction=(
            "Add the key to the app_environment block in infrastructure/*/main.tf. "
            "If it is intentionally dev-local, add it to DEV_LOCAL_KEYS."
        ),
        rationale=(
            "Every non-sensitive config key in .env.example must appear in "
            "Terraform app_environment. Agents update the env file for local dev "
            "but forget Terraform — the cluster then fails on the next deploy."
        ),
    ),
]

WORKSPACE = "."
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
