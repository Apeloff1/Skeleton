"""Canonical LLM provider boundary for the backend.

Provider-specific SDK objects stay behind this module. Request handlers and
legacy call sites should depend on the neutral request/response contract here
instead of importing vendor SDKs directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import os
import time
from typing import Any, Iterable, Mapping, Sequence


_ALLOWED_HISTORY_ROLES = frozenset({"user", "assistant"})
_DEFAULT_HISTORY_CHAR_BUDGET = 80_000


class ProviderError(RuntimeError):
    """Base class for provider-boundary failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when the selected provider cannot be used."""


class ProviderInvocationError(ProviderError):
    """Raised when a configured provider fails to return usable output."""


@dataclass(frozen=True, slots=True)
class AIMessage:
    """Provider-neutral conversation message."""

    role: str
    content: str

    def as_openai_input(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Provider-neutral text generation request."""

    instructions: str
    prompt: str
    history: tuple[AIMessage, ...] = field(default_factory=tuple)
    max_output_tokens: int | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized provider result returned to application code."""

    text: str
    provider: str
    model: str
    request_id: str | None = None
    latency_ms: float | None = None


class ProviderAdapter(ABC):
    """Minimal contract implemented by concrete model providers."""

    provider_id: str
    model: str

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this adapter has enough configuration to execute requests."""

    @abstractmethod
    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Execute one generation request and normalize the provider response."""

    def status(self) -> dict[str, Any]:
        return {"id": self.provider_id, "model": self.model, "available": self.available}


def normalize_history(
    history: Iterable[Mapping[str, Any]] | None,
    *,
    char_budget: int = _DEFAULT_HISTORY_CHAR_BUDGET,
) -> tuple[AIMessage, ...]:
    """Normalize untrusted chat history into a bounded provider-neutral form."""

    if not history or char_budget <= 0:
        return ()

    normalized: list[AIMessage] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        raw_role = item.get("role")
        raw_content = item.get("content")
        if not isinstance(raw_role, str) or not isinstance(raw_content, str):
            continue
        role = raw_role.strip().lower()
        content = raw_content.strip()
        if role not in _ALLOWED_HISTORY_ROLES or not content:
            continue
        normalized.append(AIMessage(role=role, content=content))

    kept_reversed: list[AIMessage] = []
    used = 0
    for message in reversed(normalized):
        remaining = char_budget - used
        if remaining <= 0:
            break
        content = message.content
        if len(content) > remaining:
            content = content[-remaining:]
        kept_reversed.append(AIMessage(role=message.role, content=content))
        used += len(content)

    return tuple(reversed(kept_reversed))


def _validate_request(request: ProviderRequest, *, default_model: str) -> str:
    """Validate provider-neutral request fields before any provider I/O."""

    if not isinstance(request.prompt, str) or not request.prompt.strip():
        raise ProviderInvocationError("model provider prompt must be non-empty text")

    for message in request.history:
        if not isinstance(message, AIMessage):
            raise ProviderInvocationError("model provider history contains an invalid message")
        if message.role not in _ALLOWED_HISTORY_ROLES:
            raise ProviderInvocationError("model provider history contains an invalid role")
        if not isinstance(message.content, str) or not message.content.strip():
            raise ProviderInvocationError("model provider history contains empty content")

    max_output_tokens = request.max_output_tokens
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens <= 0
    ):
        raise ProviderInvocationError("max_output_tokens must be a positive integer")

    if request.model is None:
        model = default_model
    elif not isinstance(request.model, str) or not request.model.strip():
        raise ProviderInvocationError("model provider model must be non-empty text")
    else:
        model = request.model.strip()

    if not model:
        raise ProviderInvocationError("model provider model must be non-empty text")
    return model


class OpenAIProviderAdapter(ProviderAdapter):
    """OpenAI Responses API adapter with lazy SDK construction."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("AI_MODEL") or "gpt-5.5").strip()
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "")).strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self._client = client
        self._sdk_import_error: Exception | None = None

    @property
    def available(self) -> bool:
        if self._client is not None:
            return True
        if not self.api_key:
            return False
        try:
            self._load_client_class()
        except ProviderUnavailableError:
            return False
        return True

    def _load_client_class(self) -> Any:
        if self._sdk_import_error is not None:
            raise ProviderUnavailableError("OpenAI SDK is not available") from self._sdk_import_error
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # pragma: no cover
            self._sdk_import_error = exc
            raise ProviderUnavailableError("OpenAI SDK is not available") from exc
        return AsyncOpenAI

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")

        async_openai = self._load_client_class()
        kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = async_openai(**kwargs)
        return self._client

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = _validate_request(request, default_model=self.model)
        client = self._get_client()
        messages: list[dict[str, str]] = [message.as_openai_input() for message in request.history]
        messages.append({"role": "user", "content": request.prompt})

        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": request.instructions,
            "input": messages,
        }
        if request.max_output_tokens is not None:
            kwargs["max_output_tokens"] = request.max_output_tokens

        started = time.perf_counter()
        try:
            response = await client.responses.create(**kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderInvocationError("model provider request failed") from exc

        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            raise ProviderInvocationError("model provider returned an empty response")

        request_id = getattr(response, "id", None)
        latency_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(
            text=text,
            provider=self.provider_id,
            model=model,
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_ms, 2),
        )


class ProviderRegistry:
    """Configuration-driven provider selector used by backend call sites."""

    def __init__(self, adapters: Sequence[ProviderAdapter], *, active: str) -> None:
        self._adapters = {adapter.provider_id: adapter for adapter in adapters}
        self.active_id = active.strip().lower()

    @classmethod
    def from_env(cls) -> "ProviderRegistry":
        active = os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai"
        timeout = _env_float("AI_TIMEOUT_SECONDS", 45.0, minimum=1.0)
        retries = _env_int("AI_MAX_RETRIES", 2, minimum=0)
        adapter = OpenAIProviderAdapter(timeout_seconds=timeout, max_retries=retries)
        return cls([adapter], active=active)

    @property
    def active(self) -> ProviderAdapter | None:
        return self._adapters.get(self.active_id)

    @property
    def available(self) -> bool:
        adapter = self.active
        return bool(adapter and adapter.available)

    def require_active(self) -> ProviderAdapter:
        adapter = self.active
        if adapter is None:
            raise ProviderUnavailableError(f"unsupported AI provider: {self.active_id}")
        if not adapter.available:
            raise ProviderUnavailableError(f"AI provider is not configured: {self.active_id}")
        return adapter

    def statuses(self) -> list[dict[str, Any]]:
        statuses = []
        for provider_id, adapter in sorted(self._adapters.items()):
            status = adapter.status()
            status["active"] = provider_id == self.active_id
            statuses.append(status)
        return statuses


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default
