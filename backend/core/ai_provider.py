"""Canonical LLM provider boundary for the backend.

Provider-specific SDK objects stay behind this module. Request handlers and
legacy call sites should depend on the neutral request/response contract here
instead of importing vendor SDKs directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address, ip_address
import os
import socket
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from core.provider_architecture import (
    ProviderArchitectureError,
    ProviderArchitectureReceipt,
    load_provider_architecture,
)
from skeleton.vault.data_governance import (
    DataGovernanceDenied,
    ProviderTransferRequest,
    require_provider_transfer,
)


_ALLOWED_HISTORY_ROLES = frozenset({"user", "assistant"})
_DEFAULT_HISTORY_CHAR_BUDGET = 80_000
_BLOCKED_PROVIDER_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


class ProviderError(RuntimeError):
    """Base class for provider-boundary failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when the selected provider cannot be used."""


class ProviderInvocationError(ProviderError):
    """Raised when a configured provider fails to return usable output."""


class ProviderPolicyError(ProviderError):
    """Raised when governance denies a provider-bound data transfer."""


def _literal_ip_address(host: str) -> IPv4Address | IPv6Address | None:
    """Parse canonical and legacy numeric IP spellings without DNS resolution."""

    try:
        return ip_address(host)
    except ValueError:
        pass

    # POSIX inet_aton accepts legacy IPv4 spellings such as 2130706433,
    # 0177.0.0.1, and 0x7f000001. Browsers/resolvers may interpret these as
    # loopback even though ipaddress deliberately rejects them as non-canonical.
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ip_address(packed)


def _validate_provider_base_url(base_url: str) -> str:
    """Validate a configured provider endpoint before credentials can reach it.

    Custom provider endpoints are operator configuration, not request input, but
    a bad value can still redirect a long-lived API credential toward a local or
    metadata service. Keep this boundary deterministic and network-free: require
    HTTPS, forbid URL credentials and ambiguous URL components, and reject
    obvious local/non-global literal targets. Hostname DNS/rebinding behavior is
    intentionally left to the TLS-validated transport rather than resolving here
    and creating a second time-of-check/time-of-use DNS decision.
    """

    value = base_url.strip()
    if not value:
        return ""
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ProviderUnavailableError("AI provider base URL is invalid")

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ProviderUnavailableError("AI provider base URL is invalid") from exc

    if parsed.scheme.lower() != "https":
        raise ProviderUnavailableError("AI provider base URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ProviderUnavailableError("AI provider base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ProviderUnavailableError("AI provider base URL must not contain a query or fragment")

    hostname = parsed.hostname
    if not hostname:
        raise ProviderUnavailableError("AI provider base URL must include a hostname")
    try:
        parsed.port
    except ValueError as exc:
        raise ProviderUnavailableError("AI provider base URL contains an invalid port") from exc

    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ProviderUnavailableError("AI provider base URL contains an invalid hostname") from exc

    if (
        normalized_host in _BLOCKED_PROVIDER_HOSTNAMES
        or normalized_host.endswith(".localhost")
    ):
        raise ProviderUnavailableError("AI provider base URL targets a blocked local endpoint")

    literal_ip = _literal_ip_address(normalized_host)
    if literal_ip is not None and not literal_ip.is_global:
        raise ProviderUnavailableError("AI provider base URL targets a non-public IP address")

    return value


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
    data_class: str = "internal"
    purpose: str = "model-inference"
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized provider result returned to application code."""

    text: str
    provider: str
    model: str
    request_id: str | None = None
    latency_ms: float | None = None
    governance_decision_id: str | None = None
    data_class: str | None = None


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


def _normalize_history_item(item: Mapping[str, Any] | Any) -> AIMessage | None:
    if not isinstance(item, Mapping):
        return None
    raw_role = item.get("role")
    raw_content = item.get("content")
    if not isinstance(raw_role, str) or not isinstance(raw_content, str):
        return None
    role = raw_role.strip().lower()
    content = raw_content.strip()
    if role not in _ALLOWED_HISTORY_ROLES or not content:
        return None
    return AIMessage(role=role, content=content)


def normalize_history(
    history: Iterable[Mapping[str, Any]] | None,
    *,
    char_budget: int = _DEFAULT_HISTORY_CHAR_BUDGET,
) -> tuple[AIMessage, ...]:
    """Normalize untrusted chat history into a bounded provider-neutral form."""

    if history is None or char_budget <= 0:
        return ()

    # Most request histories arrive as list/tuple sequences. Walk them from
    # newest to oldest so once the retained character budget is full we can
    # stop without parsing, allocating, or retaining the older prefix.
    if isinstance(history, SequenceABC):
        kept_reversed: list[AIMessage] = []
        used = 0
        for item in reversed(history):
            message = _normalize_history_item(item)
            if message is None:
                continue
            remaining = char_budget - used
            if remaining <= 0:
                break
            if len(message.content) > remaining:
                message = AIMessage(
                    role=message.role,
                    content=message.content[-remaining:],
                )
            kept_reversed.append(message)
            used += len(message.content)
            if used >= char_budget:
                break
        return tuple(reversed(kept_reversed))

    # Generic iterables cannot be traversed backwards. Keep only a rolling
    # character-bounded tail instead of materializing the entire normalized
    # history before applying the budget.
    kept: deque[AIMessage] = deque()
    used = 0
    for item in history:
        message = _normalize_history_item(item)
        if message is None:
            continue
        kept.append(message)
        used += len(message.content)
        overflow = used - char_budget
        while overflow > 0 and kept:
            oldest = kept[0]
            oldest_len = len(oldest.content)
            if oldest_len <= overflow:
                used -= oldest_len
                kept.popleft()
                overflow = used - char_budget
                continue
            kept[0] = AIMessage(
                role=oldest.role,
                content=oldest.content[overflow:],
            )
            used -= overflow
            overflow = 0

    return tuple(kept)


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

    if not isinstance(request.data_class, str) or not request.data_class.strip():
        raise ProviderPolicyError("model provider data classification is invalid")
    if not isinstance(request.purpose, str) or not request.purpose.strip():
        raise ProviderPolicyError("model provider transfer purpose is invalid")
    if request.tenant_id is not None and (
        not isinstance(request.tenant_id, str) or not request.tenant_id.strip()
    ):
        raise ProviderPolicyError("model provider tenant identity is invalid")
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
        self._provider_architecture_receipt: ProviderArchitectureReceipt | None = None

    def _ensure_architecture(self) -> ProviderArchitectureReceipt:
        receipt = self._provider_architecture_receipt
        if receipt is not None:
            return receipt
        try:
            receipt = load_provider_architecture(self.provider_id)
        except ProviderArchitectureError as exc:
            raise ProviderUnavailableError(
                f"AI provider architecture acknowledgement failed: {self.provider_id}"
            ) from exc
        self._provider_architecture_receipt = receipt
        return receipt

    @property
    def available(self) -> bool:
        if self._client is None and not self.api_key:
            return False
        try:
            self._ensure_architecture()
            _validate_provider_base_url(self.base_url)
            if self._client is None:
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
        self._ensure_architecture()
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")

        validated_base_url = _validate_provider_base_url(self.base_url)
        async_openai = self._load_client_class()
        kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        if validated_base_url:
            kwargs["base_url"] = validated_base_url
        self._client = async_openai(**kwargs)
        return self._client

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = _validate_request(request, default_model=self.model)
        try:
            governance = require_provider_transfer(
                ProviderTransferRequest(
                    provider_id=self.provider_id,
                    data_class=request.data_class,
                    purpose=request.purpose,
                    tenant_id=request.tenant_id,
                    source="backend/core/ai_provider.py",
                )
            )
        except DataGovernanceDenied as exc:
            raise ProviderPolicyError(
                "model provider transfer denied by governance policy"
            ) from exc
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
            governance_decision_id=governance.decision_id,
            data_class=governance.data_class,
        )


class ProviderRegistry:
    """Configuration-driven provider selector with mandatory architecture read."""

    def __init__(
        self,
        adapters: Sequence[ProviderAdapter],
        *,
        active: str,
        architecture_loader: Callable[[str], ProviderArchitectureReceipt] = load_provider_architecture,
    ) -> None:
        self._adapters = {adapter.provider_id: adapter for adapter in adapters}
        self.active_id = active.strip().lower()
        self._architecture_loader = architecture_loader
        self._architecture_receipts: dict[str, ProviderArchitectureReceipt] = {}

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

    def _architecture_receipt(self, provider_id: str) -> ProviderArchitectureReceipt:
        receipt = self._architecture_receipts.get(provider_id)
        if receipt is not None:
            return receipt
        try:
            receipt = self._architecture_loader(provider_id)
        except ProviderArchitectureError as exc:
            raise ProviderUnavailableError(
                f"AI provider architecture acknowledgement failed: {provider_id}"
            ) from exc
        if receipt.provider_id != provider_id:
            raise ProviderUnavailableError(
                f"AI provider architecture receipt identity mismatch: {provider_id}"
            )
        self._architecture_receipts[provider_id] = receipt
        return receipt

    @property
    def available(self) -> bool:
        adapter = self.active
        if adapter is None or not adapter.available:
            return False
        try:
            self._architecture_receipt(self.active_id)
        except ProviderUnavailableError:
            return False
        return True

    def require_active(self) -> ProviderAdapter:
        adapter = self.active
        if adapter is None:
            raise ProviderUnavailableError(f"unsupported AI provider: {self.active_id}")
        self._architecture_receipt(self.active_id)
        if not adapter.available:
            raise ProviderUnavailableError(f"AI provider is not configured: {self.active_id}")
        return adapter

    def architecture_receipt(self, provider_id: str | None = None) -> dict[str, Any]:
        target = (provider_id or self.active_id).strip().lower()
        if target not in self._adapters:
            raise ProviderUnavailableError(f"unsupported AI provider: {target}")
        return self._architecture_receipt(target).as_dict()

    def statuses(self) -> list[dict[str, Any]]:
        statuses = []
        for provider_id, adapter in sorted(self._adapters.items()):
            status = adapter.status()
            status["active"] = provider_id == self.active_id
            try:
                receipt = self._architecture_receipt(provider_id)
            except ProviderUnavailableError:
                status["architecture_acknowledged"] = False
                status["architecture_tag"] = None
                status["construction_version"] = None
            else:
                status["architecture_acknowledged"] = True
                status["architecture_tag"] = receipt.architecture_tag
                status["construction_version"] = receipt.construction_version
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
