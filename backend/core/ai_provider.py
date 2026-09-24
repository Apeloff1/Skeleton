"""Compatibility facade for the engine-owned AI provider runtime.

Canonical provider execution now lives in :mod:`skeleton.provider_runtime`.
Backend imports are retained so existing routes/services can migrate without a
flag day. This module must not acquire credentials, SDK imports, provider
network policy, or provider business logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from skeleton import provider_runtime as _runtime

from core.engine_client import (
    EngineClient,
    EngineClientConfig,
    EngineClientError,
    EngineDeadlineExceeded,
    EngineExecutionFailed,
    EngineUnavailable,
    engine_command_from_provider_request,
)

AIMessage = _runtime.AIMessage
FinishReason = _runtime.FinishReason
ProviderUsage = _runtime.ProviderUsage
OpenAIProviderAdapter = _runtime.OpenAIProviderAdapter
ProviderAdapter = _runtime.ProviderAdapter
ProviderError = _runtime.ProviderError
ProviderImageRequest = _runtime.ProviderImageRequest
ProviderImageResponse = _runtime.ProviderImageResponse
ProviderInvocationError = _runtime.ProviderInvocationError
ProviderPolicyError = _runtime.ProviderPolicyError
ProviderRequest = _runtime.ProviderRequest
ProviderResponse = _runtime.ProviderResponse
ProviderSpeechRequest = _runtime.ProviderSpeechRequest
ProviderSpeechResponse = _runtime.ProviderSpeechResponse
ProviderUnavailableError = _runtime.ProviderUnavailableError
normalize_history = _runtime.normalize_history
provider_request_from_context = _runtime.provider_request_from_context


class EngineProviderAdapter(ProviderAdapter):
    """Backend compatibility adapter whose execution lives in Skeleton."""

    provider_id = "openai"
    model = "engine-routed"

    def __init__(
        self,
        *,
        client: EngineClient | None = None,
        configuration_error: Exception | None = None,
    ) -> None:
        self._client = client
        self._configuration_error = configuration_error

    @classmethod
    def from_env(cls) -> "EngineProviderAdapter":
        try:
            return cls(
                client=EngineClient(
                    EngineClientConfig.from_env()
                )
            )
        except Exception as exc:
            return cls(configuration_error=exc)

    @property
    def available(self) -> bool:
        return self._client is not None and self._configuration_error is None

    def status(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "model": self.model,
            "available": self.available,
            "execution_owner": "skeleton-engine",
        }

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise TypeError("request must be ProviderRequest")
        if not self.available or self._client is None:
            raise ProviderUnavailableError(
                "AI engine provider boundary is not configured"
            )
        deadline = request.deadline
        if deadline is None:
            wall = float(request.resource_budget.max_wall_seconds)
            deadline = datetime.now(timezone.utc) + timedelta(
                seconds=min(max(wall, 1.0), 86_400.0)
            )
        try:
            command = engine_command_from_provider_request(
                request,
                service_principal=self._client.config.service_principal,
                deadline=deadline,
            )
            result = await self._client.execute(
                command,
                deadline=deadline,
            )
        except EngineDeadlineExceeded as exc:
            raise ProviderInvocationError(
                "model provider deadline exceeded"
            ) from exc
        except EngineUnavailable as exc:
            raise ProviderUnavailableError(
                "AI engine provider boundary is unavailable"
            ) from exc
        except (EngineExecutionFailed, EngineClientError) as exc:
            raise ProviderInvocationError(
                "model provider request failed"
            ) from exc

        text = result.get("final_output")
        if not isinstance(text, str) or not text.strip():
            raise ProviderInvocationError(
                "model provider returned no final output"
            )
        usage = ProviderUsage(usage_source="unknown")
        usage_payload = result.get("usage")
        if isinstance(usage_payload, dict):
            provider_usage = usage_payload.get("provider_usage")
            if isinstance(provider_usage, list) and provider_usage:
                latest = provider_usage[-1]
                if isinstance(latest, dict):
                    try:
                        usage = ProviderUsage(
                            input_tokens=latest.get("input_tokens"),
                            output_tokens=latest.get("output_tokens"),
                            cached_input_tokens=latest.get(
                                "cached_input_tokens"
                            ),
                            reasoning_tokens=latest.get(
                                "reasoning_tokens"
                            ),
                            total_tokens=latest.get("total_tokens"),
                            estimated_cost=latest.get("estimated_cost"),
                            billed_cost=latest.get("billed_cost"),
                            currency=latest.get("currency"),
                            usage_source=str(
                                latest.get("usage_source") or "unknown"
                            ),
                        )
                    except Exception:
                        usage = ProviderUsage(usage_source="unknown")

        execution_id = command.execution_request.execution_id
        return ProviderResponse(
            text=text.strip(),
            provider="skeleton-engine",
            model=request.model or self.model,
            request_id=execution_id,
            response_id=execution_id,
            finish_reason=FinishReason.COMPLETED,
            usage=usage,
            data_class=request.data_class,
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )

    async def generate_image(self, *args, **kwargs):
        raise ProviderUnavailableError(
            "image generation requires the engine media boundary"
        )

    async def create_image_variation(self, *args, **kwargs):
        raise ProviderUnavailableError(
            "image variation requires the engine media boundary"
        )

    async def edit_image(self, *args, **kwargs):
        raise ProviderUnavailableError(
            "image editing requires the engine media boundary"
        )

    async def synthesize_speech(self, *args, **kwargs):
        raise ProviderUnavailableError(
            "speech synthesis requires the engine media boundary"
        )


class ProviderRegistry(_runtime.ProviderRegistry):
    """Backend registry: neutral API, engine-owned execution from env."""

    @classmethod
    def from_env(cls) -> "ProviderRegistry":
        adapter = EngineProviderAdapter.from_env()
        return cls(
            [adapter],
            active=adapter.provider_id,
            architecture_loader=_runtime.load_provider_architecture,
        )


# Historical compatibility exports used by focused tests and older callers.
ProviderArchitectureError = _runtime.ProviderArchitectureError
ProviderArchitectureReceipt = _runtime.ProviderArchitectureReceipt
load_provider_architecture = _runtime.load_provider_architecture
_validate_provider_base_url = _runtime._validate_provider_base_url
_validate_request = _runtime._validate_request
_estimated_input_tokens = _runtime._estimated_input_tokens
_provider_operation_id = _runtime._provider_operation_id


def __getattr__(name: str):
    """Forward transitional attribute access to the canonical runtime module."""

    return getattr(_runtime, name)


__all__ = list(_runtime.__all__)
if "EngineProviderAdapter" not in __all__:
    __all__.append("EngineProviderAdapter")
