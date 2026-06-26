from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from enforcer.types import Match, FileContext, LLMConsequence

class LLMExecutor:
    def __init__(self, concurrency: int = 5, timeout: int = 30, enabled: bool = True):
        self.concurrency = concurrency
        self.timeout = timeout
        self.enabled = enabled

    def execute(self, matches: list[Match], consequence: LLMConsequence | None,
                file_ctx: FileContext) -> list[Match]:
        if not consequence or not self.enabled or not matches:
            return matches
        if not file_ctx.raw:
            return matches

        prompt = f"{consequence.prompt}\n\n--- FILE CONTENT ---\n{file_ctx.raw}"
        provider_config = self._get_provider_config(consequence.provider)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._call_llm, consequence, prompt, provider_config): m
                for m in matches
            }
            for future in as_completed(futures):
                match = futures[future]
                try:
                    match.llm_response = future.result()
                except Exception:
                    match.llm_response = ""

        return matches

    def _call_llm(self, consequence: LLMConsequence, prompt: str, provider_config: dict) -> str:
        import httpx
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
        except Exception:
            return ""

    def _get_provider_config(self, provider: str) -> dict:
        # In production, read from opencode.json. For now, return a default.
        # This will be wired up in the config loader task.
        return {
            "baseURL": "https://chat.model.tngtech.com/v1",
            "headers": {"X-User-Agent": "OpenCode"},
        }
