"""AIHub service routed through the canonical model-provider boundary.

This module preserves the historical AIHub API while eliminating its former
"universal key" and provider-specific execution assumptions. Runtime model I/O
must pass through :class:`core.ai_provider.ProviderRegistry`, which in turn
requires a valid architecture/construction receipt before any provider can
activate.

Provider names retained in the legacy enum are descriptive compatibility values,
not declarations of runtime support. Only providers declared in
`machine/ai_app_construction.json` may report as available.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, List

from core.ai_provider import (
    ProviderError,
    ProviderRegistry,
    ProviderRequest,
)


def _llm_provider_enum():
    """Lazy import of the compatibility LLMProvider enum from server.py."""

    from server import LLMProvider  # noqa: PLC0415

    return LLMProvider


class AIHubService:
    """AI planning/suggestion hub backed by the canonical provider registry."""

    def __init__(self, *, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or ProviderRegistry.from_env()
        self.providers = self._provider_snapshot()

    @property
    def api_key(self) -> str:
        """Legacy compatibility flag without returning secret material."""

        return "configured" if self._registry.available else ""

    @property
    def available(self) -> bool:
        return self._registry.available

    def _provider_snapshot(self) -> dict[Any, dict[str, Any]]:
        LLMProvider = _llm_provider_enum()
        statuses = {
            row["id"]: row
            for row in self._registry.statuses()
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        active = self._registry.active
        active_model = active.model if active is not None else "unavailable"

        def row(provider_id: str, model: str) -> dict[str, Any]:
            status = statuses.get(provider_id)
            return {
                "model": model,
                "available": bool(status and status.get("available")),
                "declared": status is not None,
                "architecture_acknowledged": bool(
                    status and status.get("architecture_acknowledged")
                ),
            }

        return {
            LLMProvider.OPENAI: row("openai", active_model),
            LLMProvider.ANTHROPIC: row("anthropic", "undeclared"),
            LLMProvider.GOOGLE: row("google", "undeclared"),
            LLMProvider.GROK: row("grok", "undeclared"),
        }

    def provider_status(self) -> dict[str, Any]:
        """Return non-secret provider readiness and receipt metadata."""

        return {
            "active": self._registry.active_id,
            "available": self._registry.available,
            "providers": self._registry.statuses(),
        }

    async def _generate(
        self,
        *,
        instructions: str,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        adapter = self._registry.require_active()
        response = await adapter.generate(
            ProviderRequest(
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            )
        )
        return response.text

    @staticmethod
    def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
        for match in re.finditer(r"\[[\s\S]*?\]", text):
            try:
                decoded = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, list) and all(
                isinstance(item, dict) for item in decoded
            ):
                return decoded
        return None

    async def suggest_features(self, context: dict) -> List[dict]:
        """Generate feature suggestions, falling back deterministically."""

        instructions = (
            "You are an expert compiler and IDE feature analyst. "
            "Suggest concrete improvements based on the supplied usage context. "
            "Return a JSON array whose objects contain id, name, description, "
            "category, impact, and implementation_difficulty."
        )
        prompt = (
            "User context:\n"
            f"- Languages used: {context.get('languages', ['python'])}\n"
            f"- Features used: {context.get('features_used', [])}\n"
            f"- Skill level: {context.get('skill_level', 'intermediate')}\n"
            f"- Current installed packs: {context.get('installed_packs', [])}\n\n"
            "Suggest five innovative but implementable CodeDock IDE features."
        )
        try:
            response = await self._generate(
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=1800,
            )
        except ProviderError:
            return self._get_default_suggestions()

        parsed = self._extract_json_array(response)
        return parsed if parsed is not None else self._get_default_suggestions()

    def _get_default_suggestions(self) -> List[dict]:
        return [
            {
                "id": "smart_completion",
                "name": "AI Smart Completion",
                "description": "Context-aware code completion through the canonical provider boundary",
                "category": "productivity",
                "impact": "high",
                "implementation_difficulty": "medium",
            },
            {
                "id": "code_review_bot",
                "name": "Automated Code Review",
                "description": "AI-assisted code review with security and performance evidence",
                "category": "quality",
                "impact": "high",
                "implementation_difficulty": "medium",
            },
            {
                "id": "interactive_debugger",
                "name": "Visual Debugger",
                "description": "Step-through debugging with variable inspection",
                "category": "debugging",
                "impact": "critical",
                "implementation_difficulty": "high",
            },
            {
                "id": "performance_profiler",
                "name": "Real-time Profiler",
                "description": "CPU and memory profiling with traceable bottleneck evidence",
                "category": "performance",
                "impact": "high",
                "implementation_difficulty": "high",
            },
            {
                "id": "collaborative_editing",
                "name": "Enhanced Collaboration",
                "description": "Shared development sessions with explicit authority boundaries",
                "category": "collaboration",
                "impact": "medium",
                "implementation_difficulty": "high",
            },
        ]

    async def query_sota(self, domain: str) -> dict:
        """Generate a bounded technology-analysis response for one domain."""

        instructions = (
            "You are a technology analyst specializing in programming languages, "
            "compilers, AI systems, and developer tooling. Distinguish current "
            "evidence from assumptions and avoid claiming unsupported freshness."
        )
        prompt = (
            f"Analyze state-of-the-art developments relevant to {domain}. "
            "Cover technologies/frameworks, current best practices, emerging "
            "directions, useful tools, and measurable performance techniques. "
            "Be specific and actionable."
        )
        try:
            response = await self._generate(
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=2200,
            )
        except ProviderError:
            return {
                "status": "offline",
                "domain": domain,
                "message": "provider_unavailable",
            }

        return {
            "status": "success",
            "domain": domain,
            "analysis": response,
            "provider": self._registry.active_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def auto_implement_feature(self, feature_spec: dict) -> dict:
        """Generate a construction plan; execution remains separately governed."""

        instructions = (
            "You are a software architect. Produce implementation plans, not "
            "unguarded side effects. Include architecture boundaries, APIs, UI, "
            "data, security, observability, failure modes, tests, evaluation, "
            "deployment, and rollback."
        )
        prompt = (
            "Generate an implementation plan for this feature:\n\n"
            f"Name: {feature_spec.get('name')}\n"
            f"Description: {feature_spec.get('description')}\n"
            f"Category: {feature_spec.get('category')}\n\n"
            "Align the plan with the repository construction contract."
        )
        try:
            response = await self._generate(
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=2600,
            )
        except ProviderError:
            return {"status": "offline", "message": "provider_unavailable"}

        return {
            "status": "success",
            "feature": feature_spec.get("name"),
            "implementation_plan": response,
            "estimated_complexity": feature_spec.get(
                "implementation_difficulty", "medium"
            ),
            "provider": self._registry.active_id,
        }


_AI_HUB_SINGLETON: AIHubService | None = None


def get_ai_hub() -> AIHubService:
    """Return the lazily-instantiated AIHub singleton."""

    global _AI_HUB_SINGLETON
    if _AI_HUB_SINGLETON is None:
        _AI_HUB_SINGLETON = AIHubService()
    return _AI_HUB_SINGLETON


__all__ = ["AIHubService", "get_ai_hub"]
