"""RuleRunner: applies rules to files, handles severity filtering and LLM consequence execution."""
from __future__ import annotations
from typing import Protocol, runtime_checkable
from enforcer.types import Severity, Match, FileContext, RuleType, SEVERITY_RANK, LLMConfig
from enforcer.rule import Rule
from enforcer.glob_util import glob_match as _glob_match
from enforcer.llm import LLMExecutor


@runtime_checkable
class RunnerProtocol(Protocol):
    """Public contract for rule runners: run per-file rules, metadata rules, and cross-file finalizers."""
    def run_rules_for_file(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]: ...
    def run_metadata_rules(self, shared_ctx: dict) -> list[Match]: ...
    def run_cross_file_finalizers(self, shared_ctx: dict) -> list[Match]: ...
    def run(self, file_contexts: list[FileContext], shared_ctx: dict) -> list[Match]: ...


class RuleRunner(RunnerProtocol):
    """Runs rules against files. Filters by severity, executes LLM consequences with shared context."""
    def __init__(self, rules: list[Rule], workspace: str = ".",
                 no_llm: bool = False, min_severity: Severity = Severity.INFO,
                 llm_config: LLMConfig | None = None):
        self.rules = rules
        self.workspace = workspace
        self.min_severity = min_severity
        # ponytail: split once at construction — O(n), avoids filtering per run
        self.content_rules = [r for r in rules if r.rule_type == RuleType.CONTENT]
        self.metadata_rules = [r for r in rules if r.rule_type == RuleType.METADATA]
        llm_config = llm_config or LLMConfig()
        self.llm_config = llm_config
        self.llm_executor = LLMExecutor(
            concurrency=llm_config.concurrency,
            timeout=llm_config.timeout,
            enabled=not no_llm,
            llm_config=llm_config,
        )

    def run_rules_for_file(self, file_ctx: FileContext, shared_ctx: dict) -> list[Match]:
        """Run all applicable CONTENT rules against one file. Returns list of Match objects."""
        all_matches: list[Match] = []
        for rule in self.content_rules:
            if not self._file_matches(file_ctx.path, rule):
                continue
            if SEVERITY_RANK.get(rule.severity, 0) < SEVERITY_RANK.get(self.min_severity, 0):
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
        shared_ctx["__llm_enabled__"] = self.llm_executor.enabled
        shared_ctx["__llm_config__"] = self.llm_config
        all_matches: list[Match] = []
        for rule in self.metadata_rules:
            if SEVERITY_RANK.get(rule.severity, 0) < SEVERITY_RANK.get(self.min_severity, 0):
                continue
            # ponytail: sentinel deliberately uses a string unlikely to appear in any real regex pattern; avoids false matches from RegexMatcher scanning metadata rules
            fake_ctx = FileContext(path=self.workspace, raw="__enforcer_sentinel__")
            matches = rule.check(fake_ctx, shared_ctx)
            if matches and rule.llm_consequence:
                matches = self.llm_executor.execute(matches, rule.llm_consequence, fake_ctx, shared_ctx)
            all_matches.extend(matches)
        return all_matches

    def _collect_unique_finalizers(self, rule) -> list:
        """Collect deduplicated finalizer matchers from a rule's matcher tree."""
        from enforcer.combinators.core import _collect_finalizers
        finalizers: list = []
        for matcher in rule.matchers:
            finalizers.extend(_collect_finalizers(matcher))
        seen: set[int] = set()
        unique: list = []
        for f in finalizers:
            if id(f) in seen:
                continue
            seen.add(id(f))
            unique.append(f)
        return unique

    @staticmethod
    def _filter_matches(matches: list[Match], rule: Rule) -> list[Match]:
        """Filter finalizer matches by rule's file_globs and exclude_globs."""
        filtered: list[Match] = []
        for m in matches:
            if not any(_glob_match(m.file, g) for g in rule.file_globs):
                continue
            if any(_glob_match(m.file, g) for g in rule.exclude_globs):
                continue
            filtered.append(m)
        return filtered

    @staticmethod
    def _find_file_ctx(path: str, shared_ctx: dict) -> object | None:
        """Find a FileContext in shared_ctx by path."""
        return next(
            (v for v in shared_ctx.values() if hasattr(v, "path") and v.path == path),
            None,
        )

    @staticmethod
    def _stamp_file_ctx(matches: list[Match], shared_ctx: dict) -> None:
        """Attach file_ctx from shared_ctx to each match by path."""
        for m in matches:
            ctx = RuleRunner._find_file_ctx(m.file, shared_ctx)
            if ctx:
                m.file_ctx = ctx

    def _apply_predicates(self, filtered: list[Match], rule: Rule, shared_ctx: dict) -> list[Match]:
        """Apply rule's predicates to filtered matches, stamping file_ctx from shared_ctx."""
        for pred in rule.predicates:
            self._stamp_file_ctx(filtered, shared_ctx)
            filtered = [m for m in filtered if pred.test(m)]
        return filtered

    def _process_rule_finalizers(self, rule: Rule, shared_ctx: dict) -> list[Match]:
        """Run finalizers for a single rule, returning stamped matches."""
        finalizers = self._collect_unique_finalizers(rule)
        all_matches: list[Match] = []
        for matcher in finalizers:
            matches = matcher.finalize_duplicates(shared_ctx)
            filtered = self._filter_matches(matches, rule)
            filtered = self._apply_predicates(filtered, rule, shared_ctx)
            for m in filtered:
                m.rule_id = rule.id
                m.severity = rule.severity
                m.fix_instruction = rule.fix_instruction
                m.message = rule._render_message(m)
            all_matches.extend(filtered)
        return all_matches

    def run_cross_file_finalizers(self, shared_ctx: dict) -> list[Match]:
        """Call finalize_duplicates on any matcher with that method, after all files processed."""
        all_matches: list[Match] = []
        for rule in self.content_rules:
            if SEVERITY_RANK.get(rule.severity, 0) < SEVERITY_RANK.get(self.min_severity, 0):
                continue
            if rule.diff_only:
                continue
            all_matches.extend(self._process_rule_finalizers(rule, shared_ctx))
        return all_matches

    def _file_matches(self, path: str, rule: Rule) -> bool:
        if not any(_glob_match(path, glob) for glob in rule.file_globs):
            return False
        if any(_glob_match(path, pat) for pat in rule.exclude_globs):
            return False
        return True

    def run(self, file_contexts: list[FileContext], shared_ctx: dict) -> list[Match]:
        """Run rules against multiple files. Returns aggregated list of Match objects."""
        shared_ctx["__llm_enabled__"] = self.llm_executor.enabled
        shared_ctx["__llm_config__"] = self.llm_config
        all_matches: list[Match] = []
        for ctx in file_contexts:
            matches = self.run_rules_for_file(ctx, shared_ctx)
            all_matches.extend(matches)
        all_matches.extend(self.run_cross_file_finalizers(shared_ctx))
        return all_matches
