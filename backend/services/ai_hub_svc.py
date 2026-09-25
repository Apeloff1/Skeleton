"""AIHub service routed through the canonical Skeleton engine boundary.

The historical AIHub API is preserved, but runtime model I/O is delegated
through the backend engine-text adapter. Legacy provider enum values remain
descriptive compatibility labels only and cannot select credentials or models.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, List

from core.engine_client import EngineClient, EngineClientError
from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    execute_engine_text,
)


def _llm_provider_enum():
    """Lazy import of the compatibility LLMProvider enum from server.py."""

    from server import LLMProvider  # noqa: PLC0415

    return LLMProvider


class AIHubService:
    """AI planning/suggestion hub backed by the canonical engine."""

    def __init__(
        self,
        *,
        registry: object | None = None,
        engine_executor=None,
    ) -> None:
        if registry is not None:
            raise ValueError(
                "local provider registry injection is disabled; use the canonical engine"
            )
        self._engine_executor = engine_executor or execute_engine_text
        self.providers = self._provider_snapshot()

    @property
    def api_key(self) -> str:
        """Legacy compatibility flag without returning secret material."""

        return "configured" if self.available else ""

    @property
    def available(self) -> bool:
        try:
            return EngineClient.from_env() is not None
        except EngineClientError:
            return False

    def _provider_snapshot(self) -> dict[Any, dict[str, Any]]:
        LLMProvider = _llm_provider_enum()

        def legacy_row() -> dict[str, Any]:
            return {
                "model": "engine-routed",
                "available": False,
                "declared": False,
                "architecture_acknowledged": False,
            }

        return {
            LLMProvider.OPENAI: legacy_row(),
            LLMProvider.ANTHROPIC: legacy_row(),
            LLMProvider.GOOGLE: legacy_row(),
            LLMProvider.GROK: legacy_row(),
        }

    def provider_status(self) -> dict[str, Any]:
        """Return non-secret engine readiness and ownership metadata."""

        available = self.available
        return {
            "active": "skeleton-engine" if available else None,
            "available": available,
            "providers": [
                {
                    "id": "skeleton-engine",
                    "model": "engine-routed",
                    "available": available,
                    "ownership": "engine-process",
                }
            ],
        }

    async def _generate(
        self,
        *,
        instructions: str,
        prompt: str,
        max_output_tokens: int | None = None,
        verification_profile: str = "assistant_proposal",
    ) -> str:
        material = json.dumps(
            {
                "instructions": instructions,
                "prompt": prompt,
                "max_output_tokens": max_output_tokens,
                "verification_profile": verification_profile,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        response = await self._engine_executor(
            EngineTextRequest(
                instructions=instructions,
                prompt=prompt,
                idempotency_key=(
                    "ai-hub:" + hashlib.sha256(material).hexdigest()
                ),
                actor_id="ai-hub",
                capability="assistant.compat",
                verification_profile=verification_profile,
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
        except EngineTextError:
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
                verification_profile="evidence_required",
            )
        except EngineTextError:
            return {
                "status": "offline",
                "domain": domain,
                "message": "engine_unavailable",
            }

        return {
            "status": "success",
            "domain": domain,
            "analysis": response,
            "provider": "skeleton-engine",
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
        except EngineTextError:
            return {"status": "offline", "message": "engine_unavailable"}

        return {
            "status": "success",
            "feature": feature_spec.get("name"),
            "implementation_plan": response,
            "estimated_complexity": feature_spec.get(
                "implementation_difficulty", "medium"
            ),
            "provider": "skeleton-engine",
        }


_AI_HUB_SINGLETON: AIHubService | None = None


def get_ai_hub() -> AIHubService:
    """Return the lazily-instantiated AIHub singleton."""

    global _AI_HUB_SINGLETON
    if _AI_HUB_SINGLETON is None:
        _AI_HUB_SINGLETON = AIHubService()
    return _AI_HUB_SINGLETON


__all__ = ["AIHubService", "get_ai_hub"]
