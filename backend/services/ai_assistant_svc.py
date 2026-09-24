"""
services/ai_assistant_svc.py — GROK-enhanced AI Assistant service.

Extracted from server.py (Feb 2026 Phase-9). Self-contained except for
``AIAssistantMode`` enum (still in server.py) and ``AIAssistRequest`` /
``AIAssistResponse`` Pydantic models (now in models/code_runtime.py).

Provider execution is routed through ``core.ai_provider.ProviderRegistry``.
The registry enforces the mandatory architecture/construction receipt before
provider activation, so this legacy API surface cannot become a second provider
runtime.
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import HTTPException

from core.ai_provider import (
    ProviderError,
    ProviderRegistry,
    ProviderRequest,
)
from skeleton.context.instruction_policy import INSTRUCTION_POLICIES


def _ai_modes():
    """Lazy access to server.AIAssistantMode enum."""
    from server import AIAssistantMode  # noqa: PLC0415

    return AIAssistantMode


# Pydantic request/response shapes
from models.code_runtime import AIAssistRequest, AIAssistResponse  # noqa: E402


AIAssistantMode = _ai_modes()  # eager-resolve at module-load time (server.py already loaded)
logger = logging.getLogger("CodeDock.AIAssistant")

_ASSIST_POLICY_IDS = {
    AIAssistantMode.EXPLAIN: "code.explain",
    AIAssistantMode.DEBUG: "code.debug",
    AIAssistantMode.OPTIMIZE: "code.optimize",
    AIAssistantMode.COMPLETE: "code.complete",
    AIAssistantMode.REFACTOR: "code.refactor",
    AIAssistantMode.DOCUMENT: "code.document",
    AIAssistantMode.TEST_GEN: "code.test_gen",
    AIAssistantMode.SECURITY_AUDIT: "code.security_audit",
    AIAssistantMode.CONVERT: "code.convert",
    AIAssistantMode.TEACH: "code.teach",
    AIAssistantMode.REVIEW: "code.review",
    AIAssistantMode.ARCHITECTURE: "code.architecture",
}


class AIAssistantService:
    """Legacy code-assistance surface backed by the canonical provider registry."""

    def __init__(
        self,
        *,
        registry: ProviderRegistry | None = None,
        runtime: object | None = None,
    ) -> None:
        if runtime is not None:
            raise ValueError(
                "alternate model runtimes are disabled; inject ProviderRegistry instead"
            )
        self._registry = registry or ProviderRegistry.from_env()
        self.model = os.environ.get("AI_ASSISTANT_MODEL", "gpt-4o").strip() or "gpt-4o"

    @property
    def api_key(self) -> str:
        """Legacy health compatibility without exposing credential material."""
        return "configured" if self.available else ""

    @property
    def available(self) -> bool:
        return self._registry.available

    def provider_status(self) -> dict:
        """Return non-secret provider and construction acknowledgement metadata."""
        return {
            "active": self._registry.active_id,
            "available": self._registry.available,
            "providers": self._registry.statuses(),
        }

    async def assist(self, request: AIAssistRequest) -> AIAssistResponse:
        policy_id = _ASSIST_POLICY_IDS.get(
            request.mode,
            "code.explain",
        )
        policy = INSTRUCTION_POLICIES.resolve(policy_id)

        language = request.language.value
        target_language = getattr(request.target_language, "value", None)
        target_line = (
            f"Target language: {target_language}\n"
            if target_language
            else ""
        )
        user_message = f"""Language: {language}
{target_line}
Code:
```{language}
{request.code}
```

{f'Additional Context: {request.context}' if request.context else ''}

Please provide a detailed, well-structured response."""

        try:
            adapter = self._registry.require_active()
            response = await adapter.generate(
                ProviderRequest(
                    instructions=policy.content,
                    prompt=user_message,
                    model=self.model,
                )
            )
            suggestion = response.text
            code_blocks = [
                {"language": match[0] or language, "code": match[1].strip()}
                for match in re.findall(r"```(\w+)?\n(.*?)```", suggestion, re.DOTALL)
            ]
            return AIAssistResponse(
                mode=request.mode,
                suggestion=suggestion,
                code_blocks=code_blocks,
                confidence=0.92,
                model=response.model or self.model,
            )
        except ProviderError as exc:
            logger.warning(
                "AI Assistant provider unavailable or failed: %s",
                exc.__class__.__name__,
            )
            raise HTTPException(status_code=503, detail="AI service unavailable") from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("AI Assistant provider boundary failed")
            raise HTTPException(status_code=500, detail="AI service error") from exc


# AIAssistantService instantiation (executor_factory remains in server.py shim)
ai_service = AIAssistantService()


__all__ = ["AIAssistantService", "ai_service"]
