"""RuleRunner: applies rules to files, handles severity filtering and LLM consequence execution."""
from __future__ import annotations
from enforcer.types import Severity, Match, FileContext, RuleType
from enforcer.rule import Rule, _glob_match
from enforcer.llm import LLMExecutor

_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}

class RuleRunner:
    """Runs rules against files. Filters by severity, executes LLM consequences with shared context."""
    def __init__(self, rules: list[Rule], workspace: str = ".",
                 no_llm: bool = False, min_severity: Severity = Severity.INFO,
                 llm_config: dict | None = None):
        self.rules = rules
        self.workspace = workspace
        self.min_severity = min_severity
        # ponytail: split once at construction — O(n), avoids filtering per run
        self.content_rules = [r for r in rules if r.rule_type == RuleType.CONTENT]
        self.metadata_rules = [r for r in rules if r.rule_type == RuleType.METADATA]
        llm_config = llm_config or {"concurrency": 5, "timeout": 30}
        self.llm_executor = LLMExecutor(
            concurrency=llm_config.get("concurrency", 5),
            timeout=llm_config.get("timeout", 30),
            enabled=not no_llm,
        )

    def run_rules_for_file(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        """Run all applicable CONTENT rules against one file. Returns list of Match objects."""
        all_matches: list[Match] = []
        for rule in self.content_rules:
            if not self._file_matches(file_ctx.path, rule):
                continue
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            matches = rule.check(file_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, file_ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches

    def run_metadata_rules(self, shared_ctx: dict) -> list[Match]:
        """Run all METADATA rules once. Returns list of Match objects.
        Metadata rules don't operate on file contents — they read git metadata
        (branch name, commit message) via the matchers themselves. The fake
        FileContext carries the workspace path and a non-empty raw sentinel so
        matchers that gate on `file_ctx.raw` still fire."""
        all_matches: list[Match] = []
        for rule in self.metadata_rules:
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            # ponytail: raw sentinel — AlwaysMatcher/RegexMatcher gate on truthy raw
            fake_ctx = FileContext(path=self.workspace, raw="(metadata)")
            matches = rule.check(fake_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, fake_ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches

    def run_cross_file_finalizers(self, shared_ctx: dict) -> list[Match]:
        """Call finalize_duplicates on any matcher with that method, after all files processed."""
        all_matches: list[Match] = []
        for rule in self.content_rules:
            if _SEVERITY_ORDER.get(rule.severity, 0) < _SEVERITY_ORDER.get(self.min_severity, 0):
                continue
            for matcher in rule.matchers:
                if hasattr(matcher, "finalize_duplicates"):
                    matches = matcher.finalize_duplicates(shared_ctx)
                    for m in matches:
                        m.rule_id = rule.id
                        m.severity = rule.severity
                        m.fix_instruction = rule.fix_instruction
                        m.message = rule._render_message(m)
                    all_matches.extend(matches)
        return all_matches

    def _file_matches(self, path: str, rule: Rule) -> bool:
        if not any(_glob_match(path, glob) for glob in rule.file_globs):
            return False
        if any(_glob_match(path, pat) for pat in rule.exclude_globs):
            return False
        return True

    def run(self, file_contexts: list[FileContext], shared_ctx: dict) -> list[Match]:
        """Run rules against multiple files. Returns aggregated list of Match objects."""
        all_matches: list[Match] = []
        for ctx in file_contexts:
            matches = self.run_rules_for_file(ctx, shared_ctx)
            all_matches.extend(matches)
        all_matches.extend(self.run_cross_file_finalizers(shared_ctx))
        return all_matches
