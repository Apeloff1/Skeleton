from __future__ import annotations
from typing import Protocol, Optional, Any, Dict

from gameforge.agents.style_application import StyleApplicator
from gameforge.rooms.room_assignments import coder_for_tier


class LLMProvider(Protocol):
    async def complete(self, prompt: str) -> str: ...


class MockLLMProvider:
    async def complete(self, prompt: str) -> str:
        return f"[mock-llm]\n{prompt[:500]}"


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


class StyleAwareGenerator:
    def __init__(self, provider: Optional[LLMProvider] = None, specialties: Optional[dict] = None):
        self.provider = provider or MockLLMProvider()
        self.specialties = specialties or {}
        self.styles = StyleApplicator()

    def resolve_coder_key(
        self,
        room_id: str,
        *,
        coder_key: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> Optional[str]:
        if coder_key:
            return coder_key
        if tier and tier != "standard":
            return coder_for_tier(room_id, tier)
        # prefer strongest assigned tier if present
        for t in ("tier_4", "tier_3", "tier_2"):
            k = coder_for_tier(room_id, t)
            if k:
                return k
        return None

    async def generate(
        self,
        room_id: str,
        prompt: str,
        *,
        coder_key: Optional[str] = None,
        tier: Optional[str] = None,
        gen_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        spec = self.specialties.get(room_id) or {}
        title = spec.get("title") or room_id
        focus = spec.get("focus") or "general systems work"
        key = self.resolve_coder_key(room_id, coder_key=coder_key, tier=tier)
        style_section = self.styles.build_style_prompt_section(key) if key else "ACTIVE STYLE: standard"
        params = self.styles.apply_to_generation(gen_params or {}, key or "standard", strength=1.0)

        rules = [
            "Be concrete.",
            "Prefer production-quality output.",
        ]
        if params.get("prefer_simple_structures"):
            rules.append("Prefer simple, flat structures.")
        if params.get("prefer_data_oriented"):
            rules.append("Prefer data-oriented layouts and batch-friendly transforms.")
        if params.get("performance_focus"):
            rules.append("Keep performance and cache behavior in mind.")
        if params.get("require_metrics_hooks"):
            rules.append("Include observability/metrics hooks where natural.")
        if params.get("max_function_lines"):
            rules.append(f"Keep functions under ~{params['max_function_lines']} lines when practical.")

        framed = (
            f"You are generating production-quality output for room '{title}'.\n"
            f"FOCUS: {focus}\n"
            f"{style_section}\n"
            f"RULES:\n- " + "\n- ".join(rules) + "\n\n"
            f"{prompt}"
        )
        return await self.provider.complete(framed)
