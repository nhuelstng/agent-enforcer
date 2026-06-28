"""LLMExecutor: calls LLM provider on rule failure. One call per file+consequence (deduplicated). Injects shared context into prompt."""
from __future__ import annotations
import json
from enforcer.types import Match, FileContext, LLMConsequence

class LLMExecutor:
    """Executes LLM consequences. Deduplicates: one call per (file, consequence) pair. Response attached to all matches from that file."""
    def __init__(self, concurrency: int = 5, timeout: int = 30, enabled: bool = True):
        self.concurrency = concurrency
        self.timeout = timeout
        self.enabled = enabled

    def execute(self, matches: list[Match], consequence: LLMConsequence | None,
                file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Run LLM consequences for matches. Returns dict of (file, consequence) -> response."""
        if not consequence or not self.enabled or not matches:
            return matches
        if not file_ctx.raw:
            return matches

        prompt = self._build_prompt(consequence, file_ctx, shared_ctx)
        provider_config = self._get_provider_config(consequence.provider)

        try:
            response = self._call_llm(consequence, prompt, provider_config)
        except Exception:
            response = ""

        for m in matches:
            m.llm_response = response
        return matches

    def _build_prompt(self, consequence: LLMConsequence, file_ctx: FileContext,
                      shared_ctx: dict | None = None) -> str:
        """Build LLM prompt from consequence template, injecting shared context file contents."""
        prompt = f"{consequence.prompt}\n\n--- FILE CONTENT ---\n{file_ctx.raw}"
        if shared_ctx:
            for key, ctx in shared_ctx.items():
                if ctx and ctx.raw and ctx.path != file_ctx.path:
                    prompt += f"\n\n--- {ctx.path} ---\n{ctx.raw}"
        return prompt

    def _call_llm(self, consequence: LLMConsequence, prompt: str, provider_config: dict) -> str:
        import httpx
        import sys
        try:
            resp = httpx.post(
                f"{provider_config['baseURL']}/chat/completions",
                headers=provider_config.get("headers", {}),
                json={
                    "model": consequence.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=consequence.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[enforcer] LLM call failed: {e}", file=sys.stderr)
            return ""

    def _get_provider_config(self, provider: str) -> dict:
        # In production, read from opencode.json. For now, return a default.
        # This will be wired up in the config loader task.
        return {
            "baseURL": "https://chat.model.tngtech.com/v1",
            "headers": {"X-User-Agent": "OpenCode"},
        }
