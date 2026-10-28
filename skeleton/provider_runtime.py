"""Canonical AI model-provider runtime for the Skeleton engine.

Provider-specific SDK objects, credentials, governance/admission checks, and
provider network policy live behind this engine-owned boundary. Application
code may consume these neutral contracts through compatibility facades, but it
must not create a second credential-bearing provider runtime.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import io
import json
import math
import os
import platform
import socket
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib import metadata as package_metadata
from importlib.util import find_spec
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from skeleton.contracts.context import ContextEnvelope
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionLease,
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.providers.contract import (
    FinishReason,
    ProviderArchitectureError,
    ProviderArchitectureReceipt,
    ProviderDelta,
    ProviderDeltaKind,
    ProviderProtocolError,
    ProviderStructuredOutput,
    ProviderToolCall,
    ProviderToolDefinition,
    ProviderUsage,
    load_provider_architecture,
)
from skeleton.shells.cancellation import CancellationToken
from skeleton.skills.tool_contract import ToolContractError, validate_json_value
from skeleton.vault.data_governance import (
    DataGovernanceDenied,
    ProviderTransferRequest,
    require_provider_transfer,
)
from skeleton.vault.governance_registry import GovernanceContext

_ALLOWED_HISTORY_ROLES = frozenset({"user", "assistant"})
_DEFAULT_HISTORY_CHAR_BUDGET = 80_000
_MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_PROVIDER_MEDIA_BYTES = 32 * 1024 * 1024
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
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


class ProviderProtocolViolationError(ProviderInvocationError):
    """Raised when provider output violates the normalized protocol contract."""


class ProviderPolicyError(ProviderError):
    """Raised when governance or admission denies provider-bound work."""


class _ProviderUsageIncompleteError(ProviderPolicyError):
    """Raised after dispatch when token actuals are not accountable."""


def _read_provider_json(response: Any) -> Mapping[str, Any]:
    """Read one provider JSON response under the canonical hard byte budget."""

    raw = response.read(_MAX_PROVIDER_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderProtocolViolationError("model provider response exceeded size limit")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ProviderProtocolViolationError("model provider returned malformed JSON") from exc
    if not isinstance(payload, Mapping):
        raise ProviderProtocolViolationError("model provider returned malformed JSON")
    return payload


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
        _ = parsed.port
    except ValueError as exc:
        raise ProviderUnavailableError("AI provider base URL contains an invalid port") from exc

    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ProviderUnavailableError("AI provider base URL contains an invalid hostname") from exc

    if normalized_host in _BLOCKED_PROVIDER_HOSTNAMES or normalized_host.endswith(".localhost"):
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
    temperature: float | None = None
    data_class: str = "internal"
    purpose: str = "model-inference"
    tenant_id: str | None = None
    operation_id: str | None = None
    admission_operation_id: str | None = None
    execution_id: str | None = None
    turn_id: str | None = None
    estimated_cost_usd: float = 0.0
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    governance_context: GovernanceContext | None = None
    context_id: str | None = None
    context_digest: str | None = None
    context_source_snapshot: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    context_compiler_version: str | None = None
    tools: tuple[ProviderToolDefinition, ...] = field(default_factory=tuple)
    # Temporary compatibility field. It is normalized into ProviderToolDefinition
    # before provider I/O and must never escape as provider-native authority.
    tool_schemas: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    structured_output_schema: Mapping[str, Any] | None = None
    tool_choice: str = "auto"
    specific_tool_id: str | None = None
    deadline: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized provider result returned to application code."""

    text: str | None
    provider: str
    model: str
    request_id: str | None = None
    response_id: str | None = None
    structured_output: Mapping[str, Any] | None = None
    tool_calls: tuple[ProviderToolCall, ...] = field(default_factory=tuple)
    finish_reason: FinishReason = FinishReason.UNKNOWN
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    latency_ms: float | None = None
    governance_decision_id: str | None = None
    admission_decision_id: str | None = None
    data_class: str | None = None
    context_id: str | None = None
    context_digest: str | None = None
    context_source_snapshot: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    context_compiler_version: str | None = None
    execution_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        if self.execution_receipt_digest is not None and (
            not isinstance(self.execution_receipt_digest, str)
            or len(self.execution_receipt_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.execution_receipt_digest)
        ):
            raise ValueError("execution_receipt_digest must be lowercase sha256")


@dataclass(frozen=True, slots=True)
class ProviderImageRequest:
    """Provider-neutral image generation request."""

    prompt: str
    size: str = "1024x1024"
    quality: str = "standard"
    count: int = 1
    model: str = "gpt-image-1"
    data_class: str = "internal"
    purpose: str = "image-generation"
    tenant_id: str | None = None
    operation_id: str | None = None
    estimated_cost_usd: float = 0.0
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    governance_context: GovernanceContext | None = None
    deadline: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderImageResponse:
    """Normalized image result with base64 payloads kept inside the media boundary."""

    images: tuple[dict[str, Any], ...]
    provider: str
    model: str
    request_id: str | None = None
    latency_ms: float | None = None
    governance_decision_id: str | None = None
    admission_decision_id: str | None = None
    data_class: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderSpeechRequest:
    """Provider-neutral speech synthesis request."""

    text: str
    voice: str = "nova"
    speed: float = 1.0
    model: str = "tts-1-hd"
    response_format: str = "mp3"
    data_class: str = "internal"
    purpose: str = "speech-synthesis"
    tenant_id: str | None = None
    operation_id: str | None = None
    estimated_cost_usd: float = 0.0
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    governance_context: GovernanceContext | None = None
    deadline: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderSpeechResponse:
    """Normalized binary speech result."""

    audio: bytes
    provider: str
    model: str
    response_format: str
    request_id: str | None = None
    latency_ms: float | None = None
    governance_decision_id: str | None = None
    admission_decision_id: str | None = None
    data_class: str | None = None


def provider_response_deltas(
    response: ProviderResponse,
    *,
    emitted_at: datetime | None = None,
) -> tuple[ProviderDelta, ...]:
    """Convert one normalized provider response into ordered neutral deltas.

    This is deliberately a transport projection, not a durable event log. A
    caller that needs durable replay must persist its own operation events.
    Providers without native streaming can still expose the same delta contract
    by decomposing their normalized final response here.
    """

    if not isinstance(response, ProviderResponse):
        raise TypeError("response must be ProviderResponse")
    # A naive datetime silently adopts the runner's local timezone when
    # astimezone() is called. Never invent UTC evidence from that ambiguity.
    if emitted_at is not None and (
        not isinstance(emitted_at, datetime)
        or emitted_at.tzinfo is None
        or emitted_at.utcoffset() is None
    ):
        raise ProviderProtocolViolationError("emitted_at must be timezone-aware")
    instant = datetime.now(UTC) if emitted_at is None else emitted_at.astimezone(UTC)
    sequence = 0
    deltas: list[ProviderDelta] = []

    def append(kind: ProviderDeltaKind, **payload: Any) -> None:
        nonlocal sequence
        deltas.append(
            ProviderDelta(
                sequence=sequence,
                kind=kind,
                response_id=response.response_id,
                emitted_at=instant,
                **payload,
            )
        )
        sequence += 1

    if response.text is not None:
        append(ProviderDeltaKind.TEXT, text=response.text)
    if response.structured_output is not None:
        append(
            ProviderDeltaKind.STRUCTURED,
            structured_fragment=dict(response.structured_output),
        )
    for tool_call in response.tool_calls:
        append(ProviderDeltaKind.TOOL_CALL, tool_call=tool_call)
    append(ProviderDeltaKind.USAGE, usage=response.usage)
    append(ProviderDeltaKind.FINAL, finish_reason=response.finish_reason)
    return tuple(deltas)


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

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderDelta]:
        """Yield provider-neutral deltas without granting durable-stream authority.

        The default implementation is buffered and therefore works for every
        adapter. A provider-specific adapter may override this with native
        streaming so long as it emits the same neutral contract and preserves
        request governance/deadline semantics.
        """

        response = await self.generate(request)
        for delta in provider_response_deltas(response):
            yield delta

    def status(self) -> dict[str, Any]:
        return {"id": self.provider_id, "model": self.model, "available": self.available}

    async def generate_image(self, request: ProviderImageRequest) -> ProviderImageResponse:
        raise ProviderUnavailableError(f"provider does not implement image generation: {self.provider_id}")

    async def create_image_variation(
        self,
        image: bytes,
        *,
        count: int = 1,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        del image, count, size, data_class, tenant_id, operation_id, deadline
        raise ProviderUnavailableError(f"provider does not implement image variation: {self.provider_id}")

    async def edit_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mask: bytes | None = None,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        del image, prompt, mask, size, data_class, tenant_id, operation_id, deadline
        raise ProviderUnavailableError(f"provider does not implement image editing: {self.provider_id}")

    async def synthesize_speech(self, request: ProviderSpeechRequest) -> ProviderSpeechResponse:
        raise ProviderUnavailableError(f"provider does not implement speech synthesis: {self.provider_id}")


@dataclass(slots=True)
class ProviderRoutingTelemetry:
    """Identity-free counters for provider routing and failover decisions."""

    primary_attempts: int = 0
    primary_successes: int = 0
    failover_attempts: int = 0
    failover_successes: int = 0
    provider_failures: int = 0
    unavailable_skips: int = 0
    policy_denials: int = 0
    last_success_provider: str | None = None
    last_failure_kind: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_attempts": self.primary_attempts,
            "primary_successes": self.primary_successes,
            "failover_attempts": self.failover_attempts,
            "failover_successes": self.failover_successes,
            "provider_failures": self.provider_failures,
            "unavailable_skips": self.unavailable_skips,
            "policy_denials": self.policy_denials,
            "last_success_provider": self.last_success_provider,
            "last_failure_kind": self.last_failure_kind,
        }


class FailoverProviderAdapter(ProviderAdapter):
    """Provider-neutral text failover across declared canonical adapters.

    Failover is deliberately narrow: only provider availability/invocation
    failures can advance to another route. Governance, admission, schema and
    other policy failures are terminal and never get converted into a provider
    routing opportunity.
    """

    def __init__(
        self,
        primary: ProviderAdapter,
        fallbacks: Sequence[ProviderAdapter],
    ) -> None:
        if not isinstance(primary, ProviderAdapter):
            raise TypeError("primary must implement ProviderAdapter")
        normalized = tuple(fallbacks)
        if not normalized:
            raise ValueError("at least one fallback provider is required")
        seen = {primary.provider_id}
        for adapter in normalized:
            if not isinstance(adapter, ProviderAdapter):
                raise TypeError("fallbacks must implement ProviderAdapter")
            if adapter.provider_id in seen:
                raise ValueError("provider failover identities must be unique")
            seen.add(adapter.provider_id)
        self.primary = primary
        self.fallbacks = normalized
        self.provider_id = primary.provider_id
        self.model = primary.model
        self._telemetry = ProviderRoutingTelemetry()

    @property
    def available(self) -> bool:
        return any(adapter.available for adapter in (self.primary, *self.fallbacks))

    def routing_snapshot(self) -> dict[str, Any]:
        payload = self._telemetry.as_dict()
        payload.update(
            {
                "primary_provider": self.primary.provider_id,
                "fallback_providers": [adapter.provider_id for adapter in self.fallbacks],
                "available": self.available,
            }
        )
        return payload

    def status(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "model": self.model,
            "available": self.available,
            "routing": self.routing_snapshot(),
        }

    def _request_for(
        self,
        adapter: ProviderAdapter,
        request: ProviderRequest,
    ) -> ProviderRequest | None:
        if adapter is self.primary:
            return request
        if request.model is not None and request.model != self.primary.model:
            return None
        return replace(request, model=adapter.model)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise TypeError("request must be ProviderRequest")
        if not isinstance(request.resource_budget, ResourceBudget):
            raise ProviderPolicyError("model provider resource budget is invalid")
        # One operation deadline covers every route. A failure near the end
        # of the primary call cannot purchase a fresh wall-time budget.
        route_deadline = datetime.now(UTC) + timedelta(seconds=request.resource_budget.max_wall_seconds)
        if request.deadline is not None:
            _remaining_provider_timeout(request, request.resource_budget.max_wall_seconds)
            route_deadline = min(route_deadline, request.deadline.astimezone(UTC))
        request = replace(request, deadline=route_deadline)
        remaining_attempts = request.resource_budget.max_provider_attempts
        last_error: ProviderError | None = None
        candidates = (self.primary, *self.fallbacks)
        for index, adapter in enumerate(candidates):
            routed = self._request_for(adapter, request)
            if routed is None:
                continue
            if not adapter.available:
                self._telemetry.unavailable_skips += 1
                self._telemetry.last_failure_kind = "unavailable"
                continue
            _remaining_provider_timeout(routed, request.resource_budget.max_wall_seconds)
            configured_attempts = getattr(adapter, "max_retries", 0) + 1
            if type(configured_attempts) is not int or configured_attempts < 1:
                raise ProviderPolicyError("declared provider attempt limit is invalid")
            if remaining_attempts < 1:
                self._telemetry.policy_denials += 1
                self._telemetry.last_failure_kind = "attempt_budget"
                raise ProviderPolicyError("remaining provider-attempt budget cannot cover declared route")
            later_routes = sum(
                self._request_for(candidate, request) is not None for candidate in candidates[index + 1 :]
            )
            reserved_attempts = min(configured_attempts, max(1, remaining_attempts - later_routes))
            routed = replace(
                routed,
                resource_budget=replace(routed.resource_budget, max_provider_attempts=reserved_attempts),
            )
            # A failed/ambiguous invocation may have used every admitted SDK
            # retry. Reserve that ceiling before entering another provider.
            remaining_attempts -= reserved_attempts
            if index == 0:
                self._telemetry.primary_attempts += 1
            else:
                self._telemetry.failover_attempts += 1
            try:
                response = await _await_bounded_provider_call(
                    lambda selected=adapter, bound_request=routed: selected.generate(bound_request),
                    deadline=route_deadline,
                    configured_timeout=request.resource_budget.max_wall_seconds,
                    label="model provider route",
                )
            except ProviderPolicyError:
                self._telemetry.policy_denials += 1
                self._telemetry.last_failure_kind = "policy"
                raise
            except ProviderProtocolViolationError:
                self._telemetry.provider_failures += 1
                self._telemetry.last_failure_kind = "protocol"
                raise
            except ProviderUnavailableError as exc:
                self._telemetry.provider_failures += 1
                self._telemetry.last_failure_kind = "unavailable"
                last_error = exc
                continue
            except ProviderInvocationError as exc:
                self._telemetry.provider_failures += 1
                self._telemetry.last_failure_kind = "invocation"
                last_error = exc
                continue
            if not isinstance(response, ProviderResponse) or (
                response.provider != adapter.provider_id or response.model != (routed.model or adapter.model)
            ):
                raise ProviderProtocolViolationError("model provider response differs from selected route")
            if index == 0:
                self._telemetry.primary_successes += 1
            else:
                self._telemetry.failover_successes += 1
            self._telemetry.last_success_provider = response.provider
            self._telemetry.last_failure_kind = None
            return response

        if isinstance(last_error, ProviderInvocationError):
            raise ProviderInvocationError("all declared model providers failed") from last_error
        raise ProviderUnavailableError("no declared model provider is available") from last_error

    async def generate_image(
        self,
        request: ProviderImageRequest,
    ) -> ProviderImageResponse:
        return await self.primary.generate_image(request)

    async def create_image_variation(
        self,
        image: bytes,
        *,
        count: int = 1,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        return await self.primary.create_image_variation(
            image,
            count=count,
            size=size,
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            deadline=deadline,
        )

    async def edit_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mask: bytes | None = None,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        return await self.primary.edit_image(
            image,
            prompt=prompt,
            mask=mask,
            size=size,
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            deadline=deadline,
        )

    async def synthesize_speech(
        self,
        request: ProviderSpeechRequest,
    ) -> ProviderSpeechResponse:
        return await self.primary.synthesize_speech(request)


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


def _strict_json_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderPolicyError(f"{field_name} must be a JSON object")
    result = dict(value)
    try:
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProviderPolicyError(f"{field_name} must be strict JSON") from exc
    return result


def _provider_tool_definitions(
    request: ProviderRequest,
) -> tuple[ProviderToolDefinition, ...]:
    definitions: dict[str, ProviderToolDefinition] = {}

    def add(definition: ProviderToolDefinition) -> None:
        existing = definitions.get(definition.tool_id)
        if existing is not None and existing != definition:
            raise ProviderPolicyError(
                f"duplicate provider tool id has conflicting definition: {definition.tool_id}"
            )
        definitions[definition.tool_id] = definition

    for definition in request.tools:
        if not isinstance(definition, ProviderToolDefinition):
            raise ProviderPolicyError("model provider tools must contain ProviderToolDefinition values")
        add(definition)

    for raw in request.tool_schemas:
        schema = _strict_json_object(raw, "model provider tool schema")
        try:
            if isinstance(schema.get("tool_id"), str) and isinstance(schema.get("input_schema"), Mapping):
                definition = ProviderToolDefinition(
                    tool_id=schema["tool_id"],
                    description=str(schema.get("description") or schema["tool_id"]),
                    input_schema=dict(schema["input_schema"]),
                )
            elif schema.get("type") == "function" and isinstance(schema.get("function"), Mapping):
                function = dict(schema["function"])
                definition = ProviderToolDefinition(
                    tool_id=str(function.get("name") or ""),
                    description=str(function.get("description") or function.get("name") or ""),
                    input_schema=dict(function.get("parameters") or {}),
                )
            elif schema.get("type") == "function":
                definition = ProviderToolDefinition(
                    tool_id=str(schema.get("name") or ""),
                    description=str(schema.get("description") or schema.get("name") or ""),
                    input_schema=dict(schema.get("parameters") or {}),
                )
            else:
                raise ProviderProtocolError("unsupported provider tool schema")
        except (ProviderProtocolError, TypeError, ValueError) as exc:
            raise ProviderPolicyError("model provider tool schema cannot be normalized") from exc
        add(definition)

    if len(definitions) > 256:
        raise ProviderPolicyError("model provider tool count exceeds protocol limit")
    return tuple(definitions[key] for key in sorted(definitions))


def _provider_tool_payloads(
    request: ProviderRequest,
) -> list[dict[str, Any]]:
    return [definition.as_openai_tool() for definition in _provider_tool_definitions(request)]


def _provider_tool_choice_payload(
    request: ProviderRequest,
    tools: tuple[ProviderToolDefinition, ...],
) -> object | None:
    choice = str(request.tool_choice or "auto").strip().lower()
    if choice not in {"none", "auto", "required", "specific"}:
        raise ProviderPolicyError("model provider tool_choice is invalid")
    if request.specific_tool_id is not None and choice != "specific":
        raise ProviderPolicyError("specific_tool_id requires tool_choice='specific'")
    offered = {tool.tool_id for tool in tools}
    if not offered:
        if choice in {"required", "specific"}:
            raise ProviderPolicyError("model provider tool_choice requires offered tools")
        return "none"
    if choice == "specific":
        tool_id = str(request.specific_tool_id or "").strip()
        if not tool_id or tool_id not in offered:
            raise ProviderPolicyError("specific provider tool choice must reference an offered tool")
        return {"type": "function", "name": tool_id}
    return choice


def _provider_structured_output_payload(
    request: ProviderRequest,
) -> dict[str, Any] | None:
    if request.structured_output_schema is None:
        return None
    schema = _strict_json_object(
        request.structured_output_schema,
        "structured_output_schema",
    )
    if not schema:
        raise ProviderPolicyError("structured_output_schema must not be empty")
    return {
        "format": {
            "type": "json_schema",
            "name": "skeleton_structured_output",
            "schema": schema,
            "strict": True,
        }
    }


def _remaining_deadline_timeout(
    deadline: datetime | None,
    configured_timeout: float,
    *,
    label: str,
    now: datetime | None = None,
) -> float:
    """Return a hard per-call timeout bounded by an optional absolute deadline."""

    timeout = float(configured_timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ProviderPolicyError(f"{label} timeout must be finite and positive")
    if deadline is None:
        return timeout
    if not isinstance(deadline, datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise ProviderPolicyError(f"{label} deadline must be timezone-aware")
    instant = datetime.now(UTC) if now is None else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ProviderPolicyError(f"{label} clock must be timezone-aware")
    remaining = (deadline.astimezone(UTC) - instant.astimezone(UTC)).total_seconds()
    if remaining <= 0:
        raise ProviderInvocationError(f"{label} deadline exceeded")
    return max(0.001, min(timeout, remaining))


def _remaining_provider_timeout(
    request: ProviderRequest,
    configured_timeout: float,
) -> float:
    return _remaining_deadline_timeout(
        request.deadline,
        configured_timeout,
        label="model provider",
    )


async def _await_bounded_provider_call(
    factory: Callable[[], Any],
    *,
    deadline: datetime | None,
    configured_timeout: float,
    label: str,
) -> Any:
    """Execute one provider coroutine under a hard timeout/deadline fence.

    The factory is invoked only after the deadline is proven live, so expired
    work never reaches provider I/O. Timeout cancellation is translated into a
    provider-boundary error while external task cancellation is deliberately
    allowed to propagate unchanged.
    """

    if not callable(factory):
        raise TypeError("provider call factory must be callable")
    timeout = _remaining_deadline_timeout(
        deadline,
        configured_timeout,
        label=label,
    )
    try:
        awaitable = factory()
        if not inspect.isawaitable(awaitable):
            raise ProviderInvocationError(f"{label} call factory did not return an awaitable")
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except TimeoutError as exc:
        raise ProviderInvocationError(f"{label} deadline exceeded") from exc


def _provider_field(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _provider_output_items(response: object) -> tuple[object, ...]:
    output = _provider_field(response, "output", ())
    if output is None:
        return ()
    if isinstance(output, SequenceABC) and not isinstance(output, (str, bytes, bytearray)):
        return tuple(output)
    return ()


def _provider_tool_call_from_item(
    item: object,
    *,
    offered_tool_ids: frozenset[str],
) -> ProviderToolCall | None:
    item_type = str(_provider_field(item, "type", "") or "").strip().lower()
    if item_type not in {"function_call", "tool_call"}:
        return None
    call_id = str(_provider_field(item, "call_id", None) or _provider_field(item, "id", None) or "").strip()
    tool_id = str(_provider_field(item, "name", None) or _provider_field(item, "tool_id", None) or "").strip()
    if not call_id or not tool_id:
        raise ProviderProtocolViolationError("model provider returned malformed tool call")
    if tool_id not in offered_tool_ids:
        raise ProviderProtocolViolationError("model provider returned an unoffered tool call")
    raw_arguments = _provider_field(item, "arguments", {})
    if isinstance(raw_arguments, str):
        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolViolationError("model provider returned malformed tool arguments") from exc
    else:
        parsed_arguments = raw_arguments
    if not isinstance(parsed_arguments, Mapping):
        raise ProviderProtocolViolationError("model provider tool arguments must be a JSON object")
    try:
        return ProviderToolCall(
            call_id=call_id,
            tool_id=tool_id,
            arguments=dict(parsed_arguments),
        )
    except ProviderProtocolError as exc:
        raise ProviderProtocolViolationError("model provider returned invalid normalized tool call") from exc


def _extract_provider_tool_calls(
    response: object,
    *,
    offered_tools: tuple[ProviderToolDefinition, ...],
) -> tuple[ProviderToolCall, ...]:
    offered = frozenset(tool.tool_id for tool in offered_tools)
    calls: list[ProviderToolCall] = []
    seen: set[str] = set()
    for item in _provider_output_items(response):
        call = _provider_tool_call_from_item(
            item,
            offered_tool_ids=offered,
        )
        if call is None:
            continue
        if call.call_id in seen:
            raise ProviderProtocolViolationError("model provider returned duplicate tool call id")
        seen.add(call.call_id)
        calls.append(call)
        if len(calls) > 256:
            raise ProviderProtocolViolationError("model provider returned too many tool calls")
    return tuple(calls)


def _extract_provider_structured_output(
    response: object,
    *,
    requested_schema: Mapping[str, Any] | None,
    text: str | None,
) -> dict[str, Any] | None:
    parsed = _provider_field(response, "output_parsed", None)
    if parsed is not None:
        if not isinstance(parsed, Mapping):
            raise ProviderProtocolViolationError("model provider structured output is not an object")
        return _strict_json_object(
            parsed,
            "model provider structured output",
        )
    if requested_schema is None or not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderProtocolViolationError("model provider structured output is invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise ProviderProtocolViolationError("model provider structured output is not an object")
    return _strict_json_object(
        value,
        "model provider structured output",
    )


def _billing_decimal(
    value: object,
    *,
    field: str,
) -> tuple[Decimal, str] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderProtocolViolationError(f"model provider {field} is invalid")
    raw = str(value).strip()
    if not raw:
        raise ProviderProtocolViolationError(f"model provider {field} is invalid")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ProviderProtocolViolationError(f"model provider {field} is invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ProviderProtocolViolationError(f"model provider {field} is invalid")
    return parsed, raw


def _provider_billing_metadata(
    response: object,
    usage: object | None,
) -> tuple[str | None, str | None]:
    """Return one non-conflicting explicit billed USD amount, if supplied."""

    candidates: list[tuple[Decimal, str, str]] = []

    def add_usd(value: object, field: str) -> None:
        parsed = _billing_decimal(value, field=field)
        if parsed is not None:
            number, raw = parsed
            candidates.append((number, raw, "USD"))

    def add_billed(
        owner: object | None,
        *,
        field_prefix: str,
    ) -> None:
        if owner is None:
            return
        raw_cost = _provider_field(owner, "billed_cost", None)
        if raw_cost is None:
            return
        currency = _provider_field(owner, "currency", None)
        if not isinstance(currency, str) or not currency.strip():
            raise ProviderProtocolViolationError("model provider billed cost is missing currency")
        normalized_currency = currency.strip().upper()
        if normalized_currency != "USD":
            raise ProviderProtocolViolationError("model provider billed cost currency is unsupported")
        parsed = _billing_decimal(
            raw_cost,
            field=f"{field_prefix} billed cost",
        )
        assert parsed is not None
        number, raw = parsed
        candidates.append((number, raw, normalized_currency))

    if usage is not None:
        add_usd(
            _provider_field(usage, "cost_usd", None),
            "usage cost_usd",
        )
        add_billed(usage, field_prefix="usage")

    add_usd(
        _provider_field(response, "cost_usd", None),
        "response cost_usd",
    )
    add_billed(response, field_prefix="response")

    if not candidates:
        return None, None

    expected = candidates[0][0]
    if any(number != expected for number, _raw, _currency in candidates[1:]):
        raise ProviderProtocolViolationError("model provider returned conflicting billed cost metadata")

    # Preserve decimal text rather than binary-float round-tripping.
    return candidates[0][1], "USD"


def _exact_usage_token_count(value: object) -> int | None:
    """Never truncate fractional or non-finite provider accounting metadata."""
    if type(value) is int:
        return value if value >= 0 else None
    if isinstance(value, str) and value and value.isascii() and value.isdecimal():
        try:
            return int(value)
        except (ValueError, OverflowError):
            # Includes Python's bounded-decimal conversion protection.
            return None
    return None


def _normalized_provider_usage(
    response: object,
    *,
    estimated_cost_usd: float,
) -> ProviderUsage:
    usage = _provider_field(response, "usage", None)
    billed_cost, billed_currency = _provider_billing_metadata(
        response,
        usage,
    )
    if usage is None:
        source = "provider" if billed_cost is not None else "estimate"
        input_tokens = output_tokens = cached_tokens = reasoning_tokens = total = None
    else:
        source = "provider"
        input_tokens = _provider_field(usage, "input_tokens", None)
        output_tokens = _provider_field(usage, "output_tokens", None)
        total = _provider_field(usage, "total_tokens", None)
        input_details = _provider_field(usage, "input_tokens_details", None)
        output_details = _provider_field(usage, "output_tokens_details", None)
        cached_tokens = (
            _provider_field(input_details, "cached_tokens", None) if input_details is not None else None
        )
        reasoning_tokens = (
            _provider_field(output_details, "reasoning_tokens", None) if output_details is not None else None
        )

    estimated = format(float(estimated_cost_usd), ".12g") if float(estimated_cost_usd) > 0 else None
    try:
        return ProviderUsage(
            input_tokens=_exact_usage_token_count(input_tokens),
            output_tokens=_exact_usage_token_count(output_tokens),
            cached_input_tokens=_exact_usage_token_count(cached_tokens),
            reasoning_tokens=_exact_usage_token_count(reasoning_tokens),
            total_tokens=_exact_usage_token_count(total),
            estimated_cost=estimated,
            billed_cost=billed_cost,
            currency=(
                billed_currency if billed_currency is not None else ("USD" if estimated is not None else None)
            ),
            usage_source=source,
        )
    except ProviderProtocolError as exc:
        raise ProviderProtocolViolationError("model provider returned invalid usage metadata") from exc


def _normalized_finish_reason(
    response: object,
    *,
    tool_calls: tuple[ProviderToolCall, ...],
) -> FinishReason:
    if tool_calls:
        return FinishReason.TOOL_CALLS
    status = str(_provider_field(response, "status", "") or "").strip().lower()
    if status in {"cancelled", "canceled"}:
        return FinishReason.CANCELLED
    if status in {"failed", "error"}:
        return FinishReason.PROVIDER_ERROR

    for item in _provider_output_items(response):
        item_type = str(_provider_field(item, "type", "") or "").strip().lower()
        if item_type == "refusal":
            return FinishReason.REFUSAL
        content = _provider_field(item, "content", ())
        if isinstance(content, SequenceABC) and not isinstance(content, (str, bytes, bytearray)):
            for part in content:
                if str(_provider_field(part, "type", "") or "").lower() == "refusal":
                    return FinishReason.REFUSAL

    incomplete = _provider_field(response, "incomplete_details", None)
    reason = str(_provider_field(incomplete, "reason", "") or "").strip().lower()
    if reason in {"max_output_tokens", "length"}:
        return FinishReason.LENGTH
    if reason in {"content_filter", "content_filtered"}:
        return FinishReason.CONTENT_FILTERED
    if status == "completed":
        return FinishReason.COMPLETED
    return FinishReason.UNKNOWN


def _normalize_provider_interaction(
    response: object,
    request: ProviderRequest,
    *,
    text: str | None,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    tuple[ProviderToolCall, ...],
    FinishReason,
    ProviderUsage,
]:
    tools = _provider_tool_definitions(request)
    tool_calls = _extract_provider_tool_calls(
        response,
        offered_tools=tools,
    )
    structured = _extract_provider_structured_output(
        response,
        requested_schema=request.structured_output_schema,
        text=text,
    )
    finish = _normalized_finish_reason(
        response,
        tool_calls=tool_calls,
    )
    _validate_response_protocol(request, tools, tool_calls, structured, finish)
    usage = _normalized_provider_usage(
        response,
        estimated_cost_usd=request.estimated_cost_usd,
    )
    normalized_text = text.strip() if isinstance(text, str) else None
    if normalized_text == "":
        normalized_text = None
    if (
        normalized_text is None
        and structured is None
        and not tool_calls
        and finish
        not in {
            FinishReason.REFUSAL,
            FinishReason.CONTENT_FILTERED,
            FinishReason.CANCELLED,
            FinishReason.DEADLINE,
        }
    ):
        raise ProviderProtocolViolationError("model provider returned no normalized output")
    return normalized_text, structured, tool_calls, finish, usage


def _validate_response_protocol(
    request: ProviderRequest,
    tools: tuple[ProviderToolDefinition, ...],
    calls: tuple[ProviderToolCall, ...],
    structured: Mapping[str, Any] | None,
    finish: FinishReason,
) -> None:
    """Conformance is verified after normalization, never inferred from prose."""
    choice = str(request.tool_choice or "auto").strip().lower()
    _provider_tool_choice_payload(request, tools)
    blocked = finish in {
        FinishReason.REFUSAL,
        FinishReason.CONTENT_FILTERED,
        FinishReason.CANCELLED,
        FinishReason.DEADLINE,
    }
    if choice == "none" and calls:
        raise ProviderProtocolViolationError("provider returned tools when tool_choice is none")
    if choice in {"required", "specific"} and not calls and not blocked:
        raise ProviderProtocolViolationError("provider omitted required tool calls")
    if choice == "specific" and any(call.tool_id != str(request.specific_tool_id).strip() for call in calls):
        raise ProviderProtocolViolationError("provider returned a different specific tool")
    offered = {tool.tool_id: tool for tool in tools}
    try:
        for call in calls:
            definition = offered.get(call.tool_id)
            if definition is None:
                raise ProviderProtocolViolationError("provider returned an undeclared tool")
            validate_json_value(definition.input_schema, call.arguments, path="provider_tool.arguments")
        if request.structured_output_schema is not None:
            if structured is None and not calls and not blocked:
                raise ProviderProtocolViolationError("provider omitted requested structured output")
            if structured is not None:
                validate_json_value(
                    request.structured_output_schema, dict(structured), path="provider_structured_output"
                )
    except ToolContractError as exc:
        raise ProviderProtocolViolationError("provider output violates the admitted schema") from exc


def _effective_governance_fields(
    *,
    data_class: str,
    purpose: str,
    tenant_id: str | None,
    governance_context: GovernanceContext | None,
) -> tuple[str, str, str | None]:
    """Resolve effective governance fields without trusting a weaker caller label."""

    if governance_context is None:
        return data_class, purpose, tenant_id
    if not isinstance(governance_context, GovernanceContext):
        raise ProviderPolicyError("provider governance context is invalid")

    normalized_purpose = purpose.strip().lower() if isinstance(purpose, str) else ""
    if normalized_purpose != governance_context.purpose:
        raise ProviderPolicyError("provider purpose does not match governance context")
    if tenant_id is not None and tenant_id.strip() != governance_context.tenant_id:
        raise ProviderPolicyError("provider tenant does not match governance context")

    return (
        governance_context.data_class.label,
        governance_context.purpose,
        governance_context.tenant_id,
    )


def provider_context_selection(context_policy: Mapping[str, Any]) -> dict[str, str] | None:
    """Resolve current and historical selection keys without rewriting a request."""
    if not isinstance(context_policy, Mapping):
        raise ProviderUnavailableError("provider context policy is malformed")
    selections = []
    for key in ("model_selection", "provider_selection"):
        if key not in context_policy:
            continue
        selection = context_policy[key]
        if selection is not None:
            if not isinstance(selection, Mapping) or set(selection) != {"provider_id", "model_id"}:
                raise ProviderUnavailableError("model selection is malformed")
            for field_name, maximum in (("provider_id", 128), ("model_id", 256)):
                value = selection[field_name]
                if (
                    not isinstance(value, str)
                    or not value
                    or value != value.strip()
                    or len(value) > maximum
                    or any(ord(character) < 32 for character in value)
                ):
                    raise ProviderUnavailableError("model selection identity is invalid")
            selection = dict(selection)
        selections.append(selection)
    if len(selections) == 2 and selections[0] != selections[1]:
        raise ProviderUnavailableError("current and historical model selections differ")
    return selections[0] if selections else None


def provider_context_temperature(context_policy: Mapping[str, Any]) -> float | None:
    """Validate both sampling aliases; conflicting immutable policy fails closed."""
    if not isinstance(context_policy, Mapping):
        raise ProviderUnavailableError("provider context policy is malformed")
    temperatures = []
    for key in ("temperature", "provider_temperature"):
        if key not in context_policy:
            continue
        value = context_policy[key]
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 2
        ):
            raise ProviderUnavailableError("temperature is invalid")
        temperatures.append(value)
    if len(temperatures) == 2 and temperatures[0] != temperatures[1]:
        raise ProviderUnavailableError("current and historical temperatures differ")
    return temperatures[0] if temperatures else None


def _supports_temperature(model: object) -> bool:
    return isinstance(model, str) and any(
        model == family or model.startswith(family + "-") for family in ("gpt-4o", "gpt-4.1")
    )


def _validate_request(request: ProviderRequest, *, default_model: str) -> str:
    """Validate provider-neutral request fields before any provider I/O."""

    if not isinstance(request.prompt, str) or not request.prompt.strip():
        raise ProviderProtocolViolationError("model provider prompt must be non-empty text")

    for message in request.history:
        if not isinstance(message, AIMessage):
            raise ProviderProtocolViolationError("model provider history contains an invalid message")
        if message.role not in _ALLOWED_HISTORY_ROLES:
            raise ProviderProtocolViolationError("model provider history contains an invalid role")
        if not isinstance(message.content, str) or not message.content.strip():
            raise ProviderProtocolViolationError("model provider history contains empty content")

    max_output_tokens = request.max_output_tokens
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens <= 0
    ):
        raise ProviderProtocolViolationError("max_output_tokens must be a positive integer")

    if request.model is None:
        model = default_model
    elif not isinstance(request.model, str) or not request.model.strip():
        raise ProviderProtocolViolationError("model provider model must be non-empty text")
    else:
        model = request.model.strip()

    if not model:
        raise ProviderProtocolViolationError("model provider model must be non-empty text")

    if request.temperature is not None:
        if (
            isinstance(request.temperature, bool)
            or not isinstance(request.temperature, (int, float))
            or not math.isfinite(request.temperature)
            or not 0 <= request.temperature <= 2
        ):
            raise ProviderProtocolViolationError("temperature must be finite and in [0, 2]")
        if not _supports_temperature(model):
            raise ProviderPolicyError("configured model does not support request temperature")

    if not isinstance(request.purpose, str) or not request.purpose.strip():
        raise ProviderPolicyError("model provider transfer purpose is invalid")
    if request.governance_context is None:
        if not isinstance(request.data_class, str) or not request.data_class.strip():
            raise ProviderPolicyError("model provider data classification is invalid")
        if request.tenant_id is not None and (
            not isinstance(request.tenant_id, str) or not request.tenant_id.strip()
        ):
            raise ProviderPolicyError("model provider tenant identity is invalid")
    _effective_governance_fields(
        data_class=request.data_class,
        purpose=request.purpose,
        tenant_id=request.tenant_id,
        governance_context=request.governance_context,
    )
    for identity_name in ("operation_id", "execution_id", "turn_id"):
        identity = getattr(request, identity_name)
        if identity is not None and (not isinstance(identity, str) or not identity.strip()):
            raise ProviderPolicyError(f"model provider {identity_name} is invalid")
    if (request.context_id is None) != (request.context_digest is None):
        raise ProviderPolicyError("model provider context_id and context_digest must be supplied together")
    if request.context_id is not None:
        try:
            parsed_context_id = UUID(request.context_id)
        except (ValueError, AttributeError) as exc:
            raise ProviderPolicyError("model provider context identity is invalid") from exc
        if str(parsed_context_id) != request.context_id:
            raise ProviderPolicyError("model provider context identity is invalid")
        digest = request.context_digest
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ProviderPolicyError("model provider context digest is invalid")
        if not request.context_source_snapshot:
            raise ProviderPolicyError("compiled provider context requires immutable source snapshot")
        seen_snapshot_ids: set[str] = set()
        previous_snapshot_id: str | None = None
        for item in request.context_source_snapshot:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ProviderPolicyError("model provider context snapshot entries must be pairs")
            segment_id, content_digest = item
            try:
                parsed_segment_id = UUID(segment_id)
            except (ValueError, AttributeError) as exc:
                raise ProviderPolicyError(
                    "model provider context snapshot segment identity is invalid"
                ) from exc
            if str(parsed_segment_id) != segment_id:
                raise ProviderPolicyError("model provider context snapshot segment identity is invalid")
            if segment_id in seen_snapshot_ids:
                raise ProviderPolicyError("model provider context snapshot contains duplicate segment")
            if previous_snapshot_id is not None and segment_id < previous_snapshot_id:
                raise ProviderPolicyError("model provider context snapshot must be deterministically ordered")
            seen_snapshot_ids.add(segment_id)
            previous_snapshot_id = segment_id
            if (
                not isinstance(content_digest, str)
                or len(content_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in content_digest)
            ):
                raise ProviderPolicyError("model provider context snapshot digest is invalid")
        if (
            not isinstance(request.context_compiler_version, str)
            or not request.context_compiler_version.strip()
        ):
            raise ProviderPolicyError("compiled provider context requires compiler version")
    elif request.context_source_snapshot or request.context_compiler_version is not None:
        raise ProviderPolicyError("context snapshot/compiler version require context identity and digest")
    tools = _provider_tool_definitions(request)
    _provider_tool_choice_payload(request, tools)
    _provider_structured_output_payload(request)
    if request.deadline is not None:
        _remaining_provider_timeout(request, 3600.0)
    if isinstance(request.estimated_cost_usd, bool):
        raise ProviderPolicyError("model provider estimated cost is invalid")
    try:
        estimated_cost = float(request.estimated_cost_usd)
    except (TypeError, ValueError) as exc:
        raise ProviderPolicyError("model provider estimated cost is invalid") from exc
    if not math.isfinite(estimated_cost) or estimated_cost < 0:
        raise ProviderPolicyError("model provider estimated cost is invalid")
    if not isinstance(request.resource_budget, ResourceBudget):
        raise ProviderPolicyError("model provider resource budget is invalid")
    return model


def _estimated_input_tokens(request: ProviderRequest) -> int:
    characters = len(request.instructions) + len(request.prompt)
    characters += sum(len(message.content) for message in request.history)
    characters += sum(
        len(
            json.dumps(
                tool.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        for tool in _provider_tool_definitions(request)
    )
    return max(1, math.ceil(characters / 4))


_CONTEXT_DATA_CLASS_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


def _context_data_class(envelope: ContextEnvelope) -> str:
    if not envelope.selected_segments:
        return "internal"
    return max(
        (segment.data_class for segment in envelope.selected_segments),
        key=lambda label: _CONTEXT_DATA_CLASS_RANK[label],
    )


def provider_request_from_context(
    envelope: ContextEnvelope,
    *,
    purpose: str = "model-inference",
    model: str | None = None,
    max_output_tokens: int | None = None,
    estimated_cost_usd: float = 0.0,
    resource_budget: ResourceBudget | None = None,
    governance_context: GovernanceContext | None = None,
) -> ProviderRequest:
    """Project one immutable ContextEnvelope into the provider boundary."""

    if not isinstance(envelope, ContextEnvelope):
        raise TypeError("envelope must be a ContextEnvelope")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ProviderPolicyError("model provider transfer purpose is invalid")
    normalized_purpose = purpose.strip()

    for segment in envelope.selected_segments:
        if segment.purpose not in {normalized_purpose, "*"}:
            raise ProviderPolicyError("context segment purpose does not match provider request purpose")

    from skeleton.context.compiler import project_provider_context

    projection = project_provider_context(envelope)
    if not projection.prompt.strip():
        raise ProviderProtocolViolationError("compiled context requires a final canonical user message")

    reserved_output = envelope.budget.reserved_output_tokens
    requested_output = reserved_output if max_output_tokens is None else max_output_tokens
    if isinstance(requested_output, bool) or not isinstance(requested_output, int) or requested_output <= 0:
        raise ProviderPolicyError("compiled context requires a positive provider output reservation")
    if requested_output > reserved_output:
        raise ProviderPolicyError("provider output request exceeds context output reservation")

    if resource_budget is None:
        resource_budget = ResourceBudget(
            max_input_tokens=envelope.budget.input_capacity(
                tools_enabled=bool(envelope.tool_schema_segments)
            ),
            max_output_tokens=reserved_output,
        )
    if not isinstance(resource_budget, ResourceBudget):
        raise ProviderPolicyError("model provider resource budget is invalid")

    parsed_tools: list[ProviderToolDefinition] = []
    for raw in projection.tool_schema_contents:
        try:
            schema = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderPolicyError("compiled tool schema is invalid JSON") from exc
        if not isinstance(schema, Mapping) or not schema:
            raise ProviderPolicyError("compiled tool schema must be a non-empty JSON object")
        try:
            parsed_tools.append(
                ProviderToolDefinition(
                    tool_id=str(schema.get("tool_id") or ""),
                    description=str(schema.get("description") or schema.get("tool_id") or ""),
                    input_schema=dict(schema.get("input_schema") or {}),
                )
            )
        except (ProviderProtocolError, TypeError, ValueError) as exc:
            raise ProviderPolicyError("compiled tool schema cannot become provider tool definition") from exc

    request = ProviderRequest(
        instructions=projection.instructions,
        prompt=projection.prompt,
        history=tuple(AIMessage(role=item["role"], content=item["content"]) for item in projection.history),
        max_output_tokens=requested_output,
        model=model,
        data_class=_context_data_class(envelope),
        purpose=normalized_purpose,
        tenant_id=envelope.tenant_id,
        operation_id=envelope.operation_id,
        execution_id=envelope.execution_id,
        turn_id=envelope.turn_id,
        estimated_cost_usd=estimated_cost_usd,
        resource_budget=resource_budget,
        governance_context=governance_context,
        context_id=envelope.context_id,
        context_digest=envelope.context_digest,
        context_source_snapshot=envelope.source_snapshot,
        context_compiler_version=envelope.compiler_version,
        tools=tuple(parsed_tools),
    )
    projected_tokens = _estimated_input_tokens(request)
    input_capacity = envelope.budget.input_capacity(tools_enabled=bool(_provider_tool_definitions(request)))
    if projected_tokens > input_capacity:
        raise ProviderPolicyError("provider projection exceeds compiled context input capacity")
    return request


def require_provider_response_context(
    response: ProviderResponse,
    envelope: ContextEnvelope,
) -> ProviderResponse:
    """Fail closed if a provider response is detached from its compiled context."""

    if not isinstance(response, ProviderResponse):
        raise TypeError("response must be ProviderResponse")
    if not isinstance(envelope, ContextEnvelope):
        raise TypeError("envelope must be ContextEnvelope")
    if response.context_id != envelope.context_id:
        raise ProviderPolicyError("model provider response context identity mismatch")
    if response.context_digest != envelope.context_digest:
        raise ProviderPolicyError("model provider response context digest mismatch")
    if response.context_source_snapshot != envelope.source_snapshot:
        raise ProviderPolicyError("model provider response context snapshot mismatch")
    if response.context_compiler_version != envelope.compiler_version:
        raise ProviderPolicyError("model provider response compiler version mismatch")
    return response


def _provider_operation_id(request: ProviderRequest) -> str:
    if request.operation_id is not None:
        return request.operation_id.strip()
    digest = hashlib.sha256()
    digest.update(request.instructions.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(request.prompt.encode("utf-8"))
    for message in request.history:
        digest.update(b"\x1e")
        digest.update(message.role.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(message.content.encode("utf-8"))
    if request.context_digest is not None:
        digest.update(b"\x1d")
        digest.update(request.context_digest.encode("ascii"))
    for schema in request.tool_schemas:
        digest.update(b"\x1c")
        digest.update(
            json.dumps(
                dict(schema),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
    return "provider-" + digest.hexdigest()[:24]


def _provider_admission_operation_id(request: ProviderRequest) -> str:
    """Resolve one quota/admission identity without changing lineage identity."""

    if request.admission_operation_id is not None:
        value = request.admission_operation_id.strip()
        if not value:
            raise ProviderPolicyError("provider admission operation identity is invalid")
        return value
    if request.operation_id is not None:
        value = request.operation_id.strip()
        if not value:
            raise ProviderPolicyError("provider operation identity is invalid")
        return value
    return "provider-invocation-" + str(uuid4())


def _provider_usage_estimate(
    request: ProviderRequest,
    *,
    requested_output_tokens: int,
    timeout_seconds: float,
    provider_attempts: int,
) -> UsageEstimate:
    return UsageEstimate(
        input_tokens=_estimated_input_tokens(request),
        output_tokens=requested_output_tokens,
        cost_usd=float(request.estimated_cost_usd),
        wall_seconds=timeout_seconds,
        provider_attempts=max(1, provider_attempts),
    )


def _usage_int(value: object, fallback: int) -> int:
    parsed = _exact_usage_token_count(value)
    return fallback if parsed is None else parsed


def _actual_provider_usage(
    response: object,
    *,
    estimate: UsageEstimate,
    wall_seconds: float,
    attempts_used: int = 1,
    normalized_usage: ProviderUsage | None = None,
) -> UsageEstimate:
    usage = response.get("usage") if isinstance(response, Mapping) else getattr(response, "usage", None)
    if normalized_usage is not None:
        input_value = normalized_usage.input_tokens
        output_value = normalized_usage.output_tokens
        if normalized_usage.billed_cost is not None:
            if normalized_usage.currency != "USD":
                raise ProviderProtocolViolationError("normalized billed cost must use USD")
            billed = _billing_decimal(
                normalized_usage.billed_cost,
                field="normalized billed cost",
            )
            assert billed is not None
            actual_cost = float(billed[0])
        else:
            actual_cost = estimate.cost_usd
    elif isinstance(usage, Mapping):
        input_value = usage.get("input_tokens")
        output_value = usage.get("output_tokens")
        actual_cost = estimate.cost_usd
    else:
        input_value = getattr(usage, "input_tokens", None)
        output_value = getattr(usage, "output_tokens", None)
        actual_cost = estimate.cost_usd

    return UsageEstimate(
        input_tokens=_usage_int(input_value, estimate.input_tokens),
        output_tokens=_usage_int(output_value, estimate.output_tokens),
        cost_usd=actual_cost,
        wall_seconds=max(0.0, float(wall_seconds)),
        provider_attempts=max(1, int(attempts_used)),
        tool_calls=estimate.tool_calls,
        artifact_bytes=estimate.artifact_bytes,
        storage_bytes=estimate.storage_bytes,
    )


def _admit_provider_request(
    runtime: AdmissionRuntime,
    request: ProviderRequest,
    *,
    tenant_id: str | None,
    requested_output_tokens: int,
    timeout_seconds: float,
    provider_attempts: int,
) -> tuple[AdmissionLease, UsageEstimate]:
    estimate = _provider_usage_estimate(
        request,
        requested_output_tokens=requested_output_tokens,
        timeout_seconds=timeout_seconds,
        provider_attempts=provider_attempts,
    )
    try:
        lease = runtime.admit(
            AdmissionRequest(
                operation_id=_provider_admission_operation_id(request),
                tenant_id=(tenant_id or "unbound"),
                capability="model-inference",
                budget=request.resource_budget,
                estimate=estimate,
            )
        )
    except (AdmissionError, AdmissionRuntimeError) as exc:
        raise ProviderPolicyError("model provider request denied by resource admission") from exc
    return lease, estimate


def _release_provider_lease(
    runtime: AdmissionRuntime,
    lease: AdmissionLease,
) -> None:
    try:
        runtime.release(lease.operation_id)
    except AdmissionRuntimeError:
        # Preserve the provider failure as the primary error. A runtime
        # implementation must keep release idempotent/recoverable.
        pass


def _provider_usage_event_id(
    lease: AdmissionLease,
    kind: str,
) -> str:
    material = (lease.lease_id + "\x1f" + kind).encode("utf-8")
    return "provider-" + kind + "-" + hashlib.sha256(material).hexdigest()[:24]


def _meter_provider_actual_usage(
    runtime: AdmissionRuntime,
    lease: AdmissionLease,
    actual: UsageEstimate,
) -> None:
    """Persist an idempotent provider charge before terminal reconciliation."""

    if lease.quota_reservation is None:
        return
    try:
        runtime.record_usage_event(
            lease.operation_id,
            _provider_usage_event_id(lease, "actual"),
            "provider",
            actual,
        )
    except AdmissionError:
        # Completion still reconciles known actual usage and records overrun.
        runtime.metrics_registry.inc("provider.actual_usage_meter_rejected_total")
    except AdmissionRuntimeError:
        runtime.metrics_registry.inc("provider.actual_usage_meter_error_total")


def _finalize_provider_usage(
    runtime: AdmissionRuntime,
    lease: AdmissionLease,
    actual: UsageEstimate,
) -> None:
    _meter_provider_actual_usage(runtime, lease, actual)
    runtime.complete(lease.operation_id, actual)


def _quarantine_provider_usage(
    runtime: AdmissionRuntime,
    lease: AdmissionLease,
    *,
    reason: str,
) -> bool:
    """Fence ambiguous post-dispatch spend instead of treating it as zero."""

    if lease.quota_reservation is None:
        _release_provider_lease(runtime, lease)
        return False

    try:
        runtime.mark_usage_unknown(
            lease.operation_id,
            _provider_usage_event_id(lease, "unknown"),
            "provider",
            reason,
        )
        runtime.metrics_registry.inc("provider.unknown_usage_quarantined_total")
    except AdmissionRuntimeError:
        # Never release durable reservation state after ambiguous dispatch.
        runtime.metrics_registry.inc("provider.unknown_usage_marker_error_total")
    return True


def _require_accountable_provider_usage(
    runtime: AdmissionRuntime,
    lease: AdmissionLease,
    usage: ProviderUsage,
) -> None:
    """Fail closed when a durable text call lacks provider token actuals.

    Request estimates remain valid admission inputs, but they are not rewritten
    as observed token usage after a provider has returned a response.
    Compatibility runtimes without durable quota reservations retain the
    historical estimate fallback because there is no durable accounting state
    to quarantine.
    """

    if lease.quota_reservation is None:
        return
    missing: list[str] = []
    if usage.input_tokens is None:
        missing.append("input_tokens")
    if usage.output_tokens is None:
        missing.append("output_tokens")
    if not missing:
        return
    raise _ProviderUsageIncompleteError("model provider usage metadata incomplete:" + ",".join(missing))


def _media_operation_id(
    provider_id: str,
    purpose: str,
    content: bytes | str,
    operation_id: str | None,
) -> str:
    del provider_id, purpose, content
    if operation_id is not None and operation_id.strip():
        return operation_id.strip()
    return "provider-media-invocation-" + str(uuid4())


def _require_media_policy(
    *,
    provider_id: str,
    purpose: str,
    data_class: str,
    tenant_id: str | None,
    operation_id: str | None,
    content: bytes | str,
    estimated_cost_usd: float,
    resource_budget: ResourceBudget,
    governance_context: GovernanceContext | None = None,
    timeout_seconds: float,
    provider_attempts: int,
    output_tokens: int = 1,
    admission_runtime: AdmissionRuntime,
) -> tuple[Any, AdmissionLease, UsageEstimate]:
    if not isinstance(purpose, str) or not purpose.strip():
        raise ProviderPolicyError("provider media purpose is invalid")
    if governance_context is None and (not isinstance(data_class, str) or not data_class.strip()):
        raise ProviderPolicyError("provider media data classification is invalid")
    data_class, purpose, tenant_id = _effective_governance_fields(
        data_class=data_class,
        purpose=purpose,
        tenant_id=tenant_id,
        governance_context=governance_context,
    )
    if not isinstance(resource_budget, ResourceBudget):
        raise ProviderPolicyError("provider media resource budget is invalid")
    try:
        estimated_cost = float(estimated_cost_usd)
    except (TypeError, ValueError) as exc:
        raise ProviderPolicyError("provider media estimated cost is invalid") from exc
    if not math.isfinite(estimated_cost) or estimated_cost < 0:
        raise ProviderPolicyError("provider media estimated cost is invalid")

    try:
        governance = require_provider_transfer(
            ProviderTransferRequest(
                provider_id=provider_id,
                data_class=data_class,
                purpose=purpose,
                tenant_id=tenant_id,
                source="skeleton/provider_runtime.py",
            )
        )
    except DataGovernanceDenied as exc:
        raise ProviderPolicyError("provider media transfer denied by governance policy") from exc

    size_hint = len(content) if isinstance(content, bytes) else len(content.encode("utf-8"))
    estimate = UsageEstimate(
        input_tokens=max(1, math.ceil(size_hint / 4)),
        output_tokens=max(1, output_tokens),
        cost_usd=estimated_cost,
        wall_seconds=timeout_seconds,
        provider_attempts=max(1, provider_attempts),
    )
    try:
        lease = admission_runtime.admit(
            AdmissionRequest(
                operation_id=_media_operation_id(provider_id, purpose, content, operation_id),
                tenant_id=(tenant_id or "unbound"),
                capability=purpose,
                budget=resource_budget,
                estimate=estimate,
            )
        )
    except (AdmissionError, AdmissionRuntimeError) as exc:
        raise ProviderPolicyError("provider media request denied by resource admission") from exc
    return governance, lease, estimate


def _extract_b64_images(response: Any, *, fallback_prompt: str) -> tuple[dict[str, Any], ...]:
    data = getattr(response, "data", None)
    if not isinstance(data, SequenceABC) or isinstance(data, (str, bytes, bytearray)):
        raise ProviderInvocationError("image provider returned malformed response")
    images: list[dict[str, Any]] = []
    total_bytes = 0
    for item in data:
        encoded = getattr(item, "b64_json", None)
        if not isinstance(encoded, str) or not encoded.strip():
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ProviderInvocationError("image provider returned invalid base64 payload") from exc
        total_bytes += len(decoded)
        if total_bytes > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image provider response exceeded size limit")
        images.append(
            {
                "data": encoded,
                "format": "base64_png",
                "revised_prompt": str(getattr(item, "revised_prompt", None) or fallback_prompt),
            }
        )
    if not images:
        raise ProviderInvocationError("image provider returned no usable image")
    return tuple(images)


def _image_artifact_bytes(images: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for image in images:
        encoded = image.get("data")
        if not isinstance(encoded, str):
            raise ProviderInvocationError("normalized image payload is invalid")
        try:
            total += len(base64.b64decode(encoded, validate=True))
        except Exception as exc:
            raise ProviderInvocationError("normalized image payload is invalid") from exc
    return total


def _media_actual_usage(
    estimate: UsageEstimate,
    *,
    wall_seconds: float,
    artifact_bytes: int,
) -> UsageEstimate:
    return UsageEstimate(
        input_tokens=estimate.input_tokens,
        output_tokens=estimate.output_tokens,
        cost_usd=estimate.cost_usd,
        wall_seconds=max(0.0, float(wall_seconds)),
        provider_attempts=1,
        tool_calls=estimate.tool_calls,
        artifact_bytes=max(0, int(artifact_bytes)),
        storage_bytes=estimate.storage_bytes,
    )


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
        admission_runtime: AdmissionRuntime | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("AI_MODEL") or "gpt-5.5").strip()
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "")).strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self._client = client
        self._sdk_import_error: Exception | None = None
        self._provider_architecture_receipt: ProviderArchitectureReceipt | None = None
        self.admission_runtime = admission_runtime or AdmissionRuntime()

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
        effective_data_class, effective_purpose, effective_tenant_id = _effective_governance_fields(
            data_class=request.data_class,
            purpose=request.purpose,
            tenant_id=request.tenant_id,
            governance_context=request.governance_context,
        )
        try:
            governance = require_provider_transfer(
                ProviderTransferRequest(
                    provider_id=self.provider_id,
                    data_class=effective_data_class,
                    purpose=effective_purpose,
                    tenant_id=effective_tenant_id,
                    source="skeleton/provider_runtime.py",
                )
            )
        except DataGovernanceDenied as exc:
            raise ProviderPolicyError("model provider transfer denied by governance policy") from exc

        requested_output = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else min(4_096, request.resource_budget.max_output_tokens)
        )
        if requested_output < 1:
            raise ProviderPolicyError("model provider requires a positive admitted output allowance")
        request_timeout = _remaining_provider_timeout(
            request,
            self.timeout_seconds,
        )
        attempt_limit = min(self.max_retries + 1, request.resource_budget.max_provider_attempts)
        lease, estimate = _admit_provider_request(
            self.admission_runtime,
            request,
            tenant_id=effective_tenant_id,
            requested_output_tokens=requested_output,
            timeout_seconds=request_timeout,
            provider_attempts=attempt_limit,
        )

        started = time.perf_counter()
        dispatched = False
        try:
            client = self._get_client()
            if attempt_limit != self.max_retries + 1:
                configure = getattr(client, "with_options", None)
                if not callable(configure):
                    raise ProviderPolicyError("resource admission cannot enforce configured provider retry limit")
                client = configure(max_retries=attempt_limit - 1)
            messages: list[dict[str, str]] = [message.as_openai_input() for message in request.history]
            messages.append({"role": "user", "content": request.prompt})

            tools = _provider_tool_definitions(request)
            kwargs: dict[str, Any] = {
                "model": model,
                "instructions": request.instructions,
                "input": messages,
                "max_output_tokens": requested_output,
            }
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if tools:
                kwargs["tools"] = [tool.as_openai_tool() for tool in tools]
                kwargs["tool_choice"] = _provider_tool_choice_payload(
                    request,
                    tools,
                )
            structured_payload = _provider_structured_output_payload(request)
            if structured_payload is not None:
                kwargs["text"] = structured_payload

            timeout_seconds = request_timeout
            try:
                dispatched = True
                response = await _await_bounded_provider_call(
                    lambda: client.responses.create(**kwargs),
                    deadline=request.deadline,
                    configured_timeout=timeout_seconds,
                    label="model provider",
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("model provider request failed") from exc

            raw_text = getattr(response, "output_text", None)
            text, structured_output, tool_calls, finish_reason, usage = _normalize_provider_interaction(
                response,
                request,
                text=(str(raw_text) if raw_text is not None else None),
            )
            _require_accountable_provider_usage(
                self.admission_runtime,
                lease,
                usage,
            )
        except _ProviderUsageIncompleteError:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-metadata-incomplete",
            )
            raise
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _actual_provider_usage(
            response,
            estimate=estimate,
            wall_seconds=latency_seconds,
            normalized_usage=usage,
            # The SDK owns transport retry accounting. Charge its admitted
            # ceiling conservatively rather than report an unobserved one.
            attempts_used=attempt_limit,
        )
        try:
            _finalize_provider_usage(
                self.admission_runtime,
                lease,
                actual,
            )
        except AdmissionRuntimeError as exc:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-reconciliation-failed",
            )
            raise ProviderPolicyError("model provider usage reconciliation failed") from exc

        response_id = getattr(response, "id", None)
        normalized_response_id = str(response_id) if response_id else None
        return ProviderResponse(
            text=text,
            provider=self.provider_id,
            model=model,
            request_id=normalized_response_id,
            response_id=normalized_response_id,
            structured_output=structured_output,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )

    async def generate_image(self, request: ProviderImageRequest) -> ProviderImageResponse:
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ProviderInvocationError("image provider prompt must be non-empty")
        if request.count < 1 or request.count > 4:
            raise ProviderInvocationError("image provider count must be between one and four")
        if request.size not in {"256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"}:
            raise ProviderInvocationError("image provider size is unsupported")
        if request.quality not in {"standard", "hd", "low", "medium", "high", "auto"}:
            raise ProviderInvocationError("image provider quality is unsupported")

        media_timeout = _remaining_deadline_timeout(
            request.deadline,
            self.timeout_seconds,
            label="image provider",
        )
        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose=request.purpose,
            data_class=request.data_class,
            tenant_id=request.tenant_id,
            operation_id=request.operation_id,
            content=request.prompt,
            estimated_cost_usd=request.estimated_cost_usd,
            resource_budget=request.resource_budget,
            governance_context=request.governance_context,
            timeout_seconds=media_timeout,
            provider_attempts=self.max_retries + 1,
            output_tokens=request.count,
            admission_runtime=self.admission_runtime,
        )
        started = time.perf_counter()
        dispatched = False
        try:
            client = self._get_client()
            try:
                dispatched = True
                response = await _await_bounded_provider_call(
                    lambda: client.images.generate(
                        model=request.model,
                        prompt=request.prompt,
                        size=request.size,
                        quality=request.quality,
                        n=request.count,
                        response_format="b64_json",
                    ),
                    deadline=request.deadline,
                    configured_timeout=self.timeout_seconds,
                    label="image provider",
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("image provider request failed") from exc
            images = _extract_b64_images(response, fallback_prompt=request.prompt)
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            _finalize_provider_usage(
                self.admission_runtime,
                lease,
                actual,
            )
        except AdmissionRuntimeError as exc:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-reconciliation-failed",
            )
            raise ProviderPolicyError("image provider usage reconciliation failed") from exc

        request_id = getattr(response, "id", None)
        return ProviderImageResponse(
            images=images,
            provider=self.provider_id,
            model=request.model,
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
        )

    async def create_image_variation(
        self,
        image: bytes,
        *,
        count: int = 1,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        if not isinstance(image, bytes) or not image:
            raise ProviderInvocationError("image variation source must be non-empty bytes")
        if len(image) > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image variation source exceeded size limit")
        if count < 1 or count > 4:
            raise ProviderInvocationError("image variation count must be between one and four")
        if size not in {"256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"}:
            raise ProviderInvocationError("image variation size is unsupported")

        media_timeout = _remaining_deadline_timeout(
            deadline,
            self.timeout_seconds,
            label="image variation provider",
        )
        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose="image-variation",
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            content=image,
            estimated_cost_usd=0.0,
            resource_budget=ResourceBudget(),
            timeout_seconds=media_timeout,
            provider_attempts=self.max_retries + 1,
            output_tokens=count,
            admission_runtime=self.admission_runtime,
        )
        source = io.BytesIO(image)
        source.name = "image.png"
        started = time.perf_counter()
        dispatched = False
        try:
            client = self._get_client()
            try:
                dispatched = True
                response = await _await_bounded_provider_call(
                    lambda: client.images.create_variation(
                        image=source,
                        n=count,
                        size=size,
                        response_format="b64_json",
                    ),
                    deadline=deadline,
                    configured_timeout=self.timeout_seconds,
                    label="image variation provider",
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("image variation request failed") from exc
            images = _extract_b64_images(response, fallback_prompt="variation")
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            _finalize_provider_usage(
                self.admission_runtime,
                lease,
                actual,
            )
        except AdmissionRuntimeError as exc:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-reconciliation-failed",
            )
            raise ProviderPolicyError("image variation usage reconciliation failed") from exc

        request_id = getattr(response, "id", None)
        return ProviderImageResponse(
            images=images,
            provider=self.provider_id,
            model="image-variation",
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
        )

    async def edit_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mask: bytes | None = None,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        if not isinstance(image, bytes) or not image:
            raise ProviderInvocationError("image edit source must be non-empty bytes")
        if len(image) > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image edit source exceeded size limit")
        if mask is not None:
            if not isinstance(mask, bytes) or not mask:
                raise ProviderInvocationError("image edit mask must be non-empty bytes")
            if len(mask) > _MAX_PROVIDER_MEDIA_BYTES:
                raise ProviderInvocationError("image edit mask exceeded size limit")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ProviderInvocationError("image edit prompt must be non-empty")
        if size not in {"256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"}:
            raise ProviderInvocationError("image edit size is unsupported")

        media_timeout = _remaining_deadline_timeout(
            deadline,
            self.timeout_seconds,
            label="image edit provider",
        )
        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose="image-edit",
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            content=image + prompt.encode("utf-8"),
            estimated_cost_usd=0.0,
            resource_budget=ResourceBudget(),
            timeout_seconds=media_timeout,
            provider_attempts=self.max_retries + 1,
            admission_runtime=self.admission_runtime,
        )
        source = io.BytesIO(image)
        source.name = "image.png"
        kwargs: dict[str, Any] = {
            "image": source,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }
        if mask is not None:
            mask_file = io.BytesIO(mask)
            mask_file.name = "mask.png"
            kwargs["mask"] = mask_file
        started = time.perf_counter()
        dispatched = False
        try:
            client = self._get_client()
            try:
                dispatched = True
                response = await _await_bounded_provider_call(
                    lambda: client.images.edit(**kwargs),
                    deadline=deadline,
                    configured_timeout=self.timeout_seconds,
                    label="image edit provider",
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("image edit request failed") from exc
            images = _extract_b64_images(response, fallback_prompt=prompt)
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            _finalize_provider_usage(
                self.admission_runtime,
                lease,
                actual,
            )
        except AdmissionRuntimeError as exc:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-reconciliation-failed",
            )
            raise ProviderPolicyError("image edit usage reconciliation failed") from exc

        request_id = getattr(response, "id", None)
        return ProviderImageResponse(
            images=images,
            provider=self.provider_id,
            model="image-edit",
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
        )

    async def synthesize_speech(self, request: ProviderSpeechRequest) -> ProviderSpeechResponse:
        if not isinstance(request.text, str) or not request.text.strip():
            raise ProviderInvocationError("speech provider text must be non-empty")
        if len(request.text) > 16_384:
            raise ProviderInvocationError("speech provider text exceeded size limit")
        if isinstance(request.speed, bool):
            raise ProviderInvocationError("speech provider speed is unsupported")
        try:
            speed = float(request.speed)
        except (TypeError, ValueError) as exc:
            raise ProviderInvocationError("speech provider speed is unsupported") from exc
        if not math.isfinite(speed) or not 0.25 <= speed <= 4.0:
            raise ProviderInvocationError("speech provider speed is unsupported")
        if request.response_format not in {"mp3", "wav", "opus", "aac", "flac", "pcm"}:
            raise ProviderInvocationError("speech provider format is unsupported")

        media_timeout = _remaining_deadline_timeout(
            request.deadline,
            self.timeout_seconds,
            label="speech provider",
        )
        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose=request.purpose,
            data_class=request.data_class,
            tenant_id=request.tenant_id,
            operation_id=request.operation_id,
            content=request.text,
            estimated_cost_usd=request.estimated_cost_usd,
            resource_budget=request.resource_budget,
            governance_context=request.governance_context,
            timeout_seconds=media_timeout,
            provider_attempts=self.max_retries + 1,
            admission_runtime=self.admission_runtime,
        )
        started = time.perf_counter()
        dispatched = False
        try:
            client = self._get_client()
            try:
                dispatched = True
                response = await _await_bounded_provider_call(
                    lambda: client.audio.speech.create(
                        model=request.model,
                        voice=request.voice,
                        input=request.text,
                        speed=speed,
                        response_format=request.response_format,
                    ),
                    deadline=request.deadline,
                    configured_timeout=self.timeout_seconds,
                    label="speech provider",
                )
                raw = getattr(response, "content", None)
                if raw is None:
                    reader = getattr(response, "read", None)
                    if reader is None:
                        raise ProviderInvocationError("speech provider returned malformed response")
                    raw = reader()
                    if inspect.isawaitable(raw):
                        raw = await _await_bounded_provider_call(
                            lambda: raw,
                            deadline=request.deadline,
                            configured_timeout=self.timeout_seconds,
                            label="speech provider response read",
                        )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("speech provider request failed") from exc

            if not isinstance(raw, (bytes, bytearray)) or not raw:
                raise ProviderInvocationError("speech provider returned empty audio")
            audio = bytes(raw)
            if len(audio) > _MAX_PROVIDER_MEDIA_BYTES:
                raise ProviderInvocationError("speech provider response exceeded size limit")
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=len(audio),
        )
        try:
            _finalize_provider_usage(
                self.admission_runtime,
                lease,
                actual,
            )
        except AdmissionRuntimeError as exc:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-reconciliation-failed",
            )
            raise ProviderPolicyError("speech provider usage reconciliation failed") from exc

        request_id = getattr(response, "request_id", None) or getattr(response, "id", None)
        return ProviderSpeechResponse(
            audio=audio,
            provider=self.provider_id,
            model=request.model,
            response_format=request.response_format,
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
        )


class OpenAICompatibleSecondaryAdapter(OpenAIProviderAdapter):
    """Optional declared text-only secondary provider using Responses semantics."""

    provider_id = "openai-compatible-secondary"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        client: Any | None = None,
        admission_runtime: AdmissionRuntime | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
            admission_runtime=admission_runtime,
        )

    async def generate_image(
        self,
        request: ProviderImageRequest,
    ) -> ProviderImageResponse:
        del request
        raise ProviderUnavailableError("secondary provider capability is not declared: image-generation")

    async def create_image_variation(
        self,
        image: bytes,
        *,
        count: int = 1,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        del image, count, size, data_class, tenant_id, operation_id, deadline
        raise ProviderUnavailableError("secondary provider capability is not declared: image-variation")

    async def edit_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mask: bytes | None = None,
        size: str = "1024x1024",
        data_class: str = "internal",
        tenant_id: str | None = None,
        operation_id: str | None = None,
        deadline: datetime | None = None,
    ) -> ProviderImageResponse:
        del image, prompt, mask, size, data_class, tenant_id, operation_id, deadline
        raise ProviderUnavailableError("secondary provider capability is not declared: image-editing")

    async def synthesize_speech(
        self,
        request: ProviderSpeechRequest,
    ) -> ProviderSpeechResponse:
        del request
        raise ProviderUnavailableError("secondary provider capability is not declared: speech-synthesis")


class OpenAISyncProviderAdapter:
    """Dependency-free synchronous OpenAI Responses API adapter.

    Jeeves and other synchronous engine call sites use this adapter instead of
    owning credentials or raw provider HTTP behavior. It deliberately shares
    the same architecture acknowledgement, governance, admission, URL policy,
    request validation, and normalized response contract as the async adapter.
    """

    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        admission_runtime: AdmissionRuntime | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("AI_MODEL") or "gpt-5.5").strip()
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "")).strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self._provider_architecture_receipt: ProviderArchitectureReceipt | None = None
        self.admission_runtime = admission_runtime or AdmissionRuntime()

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

    def _responses_url(self) -> str:
        configured = self.base_url or _DEFAULT_OPENAI_BASE_URL
        validated = _validate_provider_base_url(configured)
        normalized = validated.rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        return normalized + "/responses"

    @property
    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._ensure_architecture()
            self._responses_url()
        except ProviderUnavailableError:
            return False
        return True

    def status(self) -> dict[str, Any]:
        return {"id": self.provider_id, "model": self.model, "available": self.available}

    @staticmethod
    def _extract_response_text(payload: Any) -> str | None:
        if not isinstance(payload, Mapping):
            raise ProviderProtocolViolationError("model provider returned malformed JSON")

        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        output = payload.get("output")
        if not isinstance(output, list):
            raise ProviderProtocolViolationError("model provider returned malformed response")

        fragments: list[str] = []
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") not in {"output_text", "text"}:
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    fragments.append(text.strip())

        joined = "\n".join(fragments).strip()
        return joined or None

    @staticmethod
    def _decode_response(response: Any) -> Mapping[str, Any]:
        return _read_provider_json(response)

    def generate_sync(
        self,
        request: ProviderRequest,
        *,
        cancellation: CancellationToken | None = None,
    ) -> ProviderResponse:
        if cancellation is not None:
            if not isinstance(cancellation, CancellationToken):
                raise TypeError("cancellation must be CancellationToken")
            cancellation.require_active()
        model = _validate_request(request, default_model=self.model)
        self._ensure_architecture()

        effective_data_class, effective_purpose, effective_tenant_id = _effective_governance_fields(
            data_class=request.data_class,
            purpose=request.purpose,
            tenant_id=request.tenant_id,
            governance_context=request.governance_context,
        )
        try:
            governance = require_provider_transfer(
                ProviderTransferRequest(
                    provider_id=self.provider_id,
                    data_class=effective_data_class,
                    purpose=effective_purpose,
                    tenant_id=effective_tenant_id,
                    source="skeleton/provider_runtime.py",
                )
            )
        except DataGovernanceDenied as exc:
            raise ProviderPolicyError("model provider transfer denied by governance policy") from exc

        requested_output = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else min(4_096, request.resource_budget.max_output_tokens)
        )
        if requested_output < 1:
            raise ProviderPolicyError("model provider requires a positive admitted output allowance")
        request_timeout = _remaining_provider_timeout(
            request,
            self.timeout_seconds,
        )
        attempt_limit = min(self.max_retries + 1, request.resource_budget.max_provider_attempts)
        lease, estimate = _admit_provider_request(
            self.admission_runtime,
            request,
            tenant_id=effective_tenant_id,
            requested_output_tokens=requested_output,
            timeout_seconds=request_timeout,
            provider_attempts=attempt_limit,
        )

        if not self.api_key:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")

        messages: list[dict[str, str]] = [message.as_openai_input() for message in request.history]
        messages.append({"role": "user", "content": request.prompt})
        tools = _provider_tool_definitions(request)
        body: dict[str, Any] = {
            "model": model,
            "instructions": request.instructions,
            "input": messages,
            "max_output_tokens": requested_output,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if tools:
            body["tools"] = [tool.as_openai_tool() for tool in tools]
            body["tool_choice"] = _provider_tool_choice_payload(
                request,
                tools,
            )
        structured_payload = _provider_structured_output_payload(request)
        if structured_payload is not None:
            body["text"] = structured_payload

        outbound = urllib.request.Request(
            self._responses_url(),
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Skeleton-Provider-Runtime/3.2",
            },
            method="POST",
        )

        started = time.perf_counter()
        last_error: BaseException | None = None
        attempts_used = 0
        dispatched = False
        try:
            for _attempt in range(attempt_limit):
                if cancellation is not None:
                    cancellation.require_active()
                attempts_used += 1
                try:
                    timeout_seconds = _remaining_provider_timeout(
                        request,
                        request_timeout,
                    )
                    if cancellation is not None:
                        cancellation.require_active()
                    dispatched = True
                    with urllib.request.urlopen(
                        outbound,
                        timeout=timeout_seconds,
                    ) as response:
                        payload = self._decode_response(response)
                    if cancellation is not None:
                        cancellation.require_active()
                    raw_text = self._extract_response_text(payload)
                    (
                        text,
                        structured_output,
                        tool_calls,
                        finish_reason,
                        usage,
                    ) = _normalize_provider_interaction(
                        payload,
                        request,
                        text=raw_text,
                    )
                    _require_accountable_provider_usage(
                        self.admission_runtime,
                        lease,
                        usage,
                    )
                    request_id = payload.get("id")
                    latency_seconds = max(0.0, time.perf_counter() - started)
                    actual = _actual_provider_usage(
                        payload,
                        estimate=estimate,
                        wall_seconds=latency_seconds,
                        attempts_used=attempts_used,
                        normalized_usage=usage,
                    )
                    if cancellation is not None:
                        cancellation.require_active()
                    try:
                        _finalize_provider_usage(
                            self.admission_runtime,
                            lease,
                            actual,
                        )
                    except AdmissionRuntimeError as exc:
                        _quarantine_provider_usage(
                            self.admission_runtime,
                            lease,
                            reason="provider-usage-reconciliation-failed",
                        )
                        raise ProviderPolicyError("model provider usage reconciliation failed") from exc
                    normalized_id = str(request_id) if isinstance(request_id, (str, int)) else None
                    return ProviderResponse(
                        text=text,
                        provider=self.provider_id,
                        model=model,
                        request_id=normalized_id,
                        response_id=normalized_id,
                        structured_output=structured_output,
                        tool_calls=tool_calls,
                        finish_reason=finish_reason,
                        usage=usage,
                        latency_ms=round(latency_seconds * 1000, 2),
                        governance_decision_id=governance.decision_id,
                        admission_decision_id=lease.decision.decision_id,
                        data_class=governance.data_class,
                        context_id=request.context_id,
                        context_digest=request.context_digest,
                        context_source_snapshot=request.context_source_snapshot,
                        context_compiler_version=request.context_compiler_version,
                    )
                except ProviderError:
                    raise
                except TimeoutError as exc:
                    if cancellation is not None and cancellation.cancelled:
                        cancellation.require_active()
                    last_error = exc
                    if request.deadline is not None:
                        deadline = request.deadline.astimezone(UTC)
                        if datetime.now(UTC) >= deadline:
                            raise ProviderInvocationError("model provider deadline exceeded") from exc
                    continue
                except (
                    urllib.error.URLError,
                    OSError,
                    ValueError,
                ) as exc:
                    if cancellation is not None and cancellation.cancelled:
                        cancellation.require_active()
                    last_error = exc
                    continue
        except _ProviderUsageIncompleteError:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-usage-metadata-incomplete",
            )
            raise
        except BaseException:
            if dispatched:
                _quarantine_provider_usage(
                    self.admission_runtime,
                    lease,
                    reason="provider-dispatch-or-response-ambiguous",
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            raise

        if dispatched:
            _quarantine_provider_usage(
                self.admission_runtime,
                lease,
                reason="provider-dispatch-or-response-ambiguous",
            )
        else:
            _release_provider_lease(self.admission_runtime, lease)
        raise ProviderInvocationError("model provider request failed") from last_error


class _GovernedLocalAdapter(ProviderAdapter):
    """Bind activated local execution to the canonical policy/accounting owner.

    The underlying adapter retains its tokenizer, workers, cache and native
    receipts. This facade grants no additional model or network authority.
    """

    provider_id = "local"

    def __init__(
        self, adapter: ProviderAdapter, *, admission_runtime: AdmissionRuntime, timeout_seconds: float
    ) -> None:
        self._adapter = adapter
        self.model = adapter.model
        self.admission_runtime = admission_runtime
        self.timeout_seconds = timeout_seconds
        self.max_retries = 0
        self._activated_model_digest = adapter.engine.model.model_digest
        self._source_model_id = adapter.engine.model.model_id
        self._architecture_receipt = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)

    def _ensure_architecture(self) -> None:
        try:
            receipt = load_provider_architecture(self.provider_id)
        except ProviderArchitectureError as exc:
            raise ProviderUnavailableError("local provider architecture acknowledgement failed") from exc
        if not isinstance(receipt, ProviderArchitectureReceipt) or receipt.provider_id != self.provider_id:
            raise ProviderUnavailableError("local provider architecture acknowledgement is invalid")
        self._architecture_receipt = receipt

    @property
    def available(self) -> bool:
        try:
            self._ensure_architecture()
            return self.model == self._adapter.model and self._adapter.available
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError):
            return False

    @property
    def supports_cooperative_cancellation(self) -> bool:
        return self._adapter.supports_cooperative_cancellation

    def execution_identity(self) -> dict[str, object]:
        self._ensure_architecture()
        try:
            backend = self.engine.model
            if (
                backend.model_digest != self._activated_model_digest
                or backend.model_id != self._source_model_id
            ):
                raise ValueError("activated model identity differs")
            check = getattr(backend, "assert_identity", None)
            if callable(check):
                check()
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
            raise ProviderUnavailableError("local artifact identity drift") from exc
        return provider_execution_identity(self)

    def status(self) -> dict[str, Any]:
        try:
            result = self._adapter.status()
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
            raise ProviderUnavailableError("local artifact identity drift") from exc
        result["available"] = self.available
        return result

    async def close(self, *, cancel_running: bool = True) -> None:
        await self._adapter.close(cancel_running=cancel_running)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        from skeleton.ai.runtime.inference.local import (
            LocalInferenceCancelled,
            _LOCAL_DISPATCH_OBSERVER,
            _LocalUsageLimitViolation,
        )

        started = time.perf_counter()
        self._ensure_architecture()
        _validate_request(request, default_model=self.model)
        if not self.available:
            raise ProviderUnavailableError("local artifact identity drift or activated model unavailable")
        data_class, purpose, tenant_id = _effective_governance_fields(
            data_class=request.data_class,
            purpose=request.purpose,
            tenant_id=request.tenant_id,
            governance_context=request.governance_context,
        )
        try:
            governance = require_provider_transfer(
                ProviderTransferRequest(
                    provider_id=self.provider_id,
                    data_class=data_class,
                    purpose=purpose,
                    tenant_id=tenant_id,
                    source="skeleton/provider_runtime.py",
                )
            )
        except DataGovernanceDenied as exc:
            raise ProviderPolicyError("local model transfer denied by governance policy") from exc
        limits = self.generation_limits()
        requested_output = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else min(256, request.resource_budget.max_output_tokens, limits["max_output_tokens"])
        )
        if type(requested_output) is not int or requested_output < 1:
            raise ProviderPolicyError("local model requires a positive admitted output allowance")
        timeout = _remaining_provider_timeout(
            request, min(self.timeout_seconds, request.resource_budget.max_wall_seconds)
        )
        execution_deadline = datetime.now(UTC) + timedelta(seconds=timeout)
        if request.deadline is not None:
            execution_deadline = min(execution_deadline, request.deadline.astimezone(UTC))
        bounded_request = replace(request, deadline=execution_deadline)
        # Local execution never reserves a caller-supplied hosted-model cost.
        lease, estimate = _admit_provider_request(
            self.admission_runtime,
            replace(request, estimated_cost_usd=0.0),
            tenant_id=tenant_id,
            requested_output_tokens=requested_output,
            timeout_seconds=timeout,
            provider_attempts=1,
        )
        dispatched = threading.Event()
        observer = _LOCAL_DISPATCH_OBSERVER.set(dispatched.set)

        def complete_usage(input_tokens: int, output_tokens: int):
            actual = UsageEstimate(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=0.0,
                wall_seconds=max(0.0, time.perf_counter() - started),
                provider_attempts=1,
            )
            try:
                _meter_provider_actual_usage(self.admission_runtime, lease, actual)
                return self.admission_runtime.complete(lease.operation_id, actual)
            except AdmissionRuntimeError as exc:
                _quarantine_provider_usage(
                    self.admission_runtime, lease, reason="local-usage-reconciliation-failed"
                )
                raise ProviderPolicyError("local model usage reconciliation failed") from exc

        try:
            response = await self._adapter.generate(bounded_request)
            if response.provider != self.provider_id or response.model != self.model:
                raise ProviderProtocolViolationError("local response differs from its activated route")
            _require_accountable_provider_usage(self.admission_runtime, lease, response.usage)
        except _LocalUsageLimitViolation as exc:
            complete_usage(exc.input_tokens, exc.output_tokens)
            raise ProviderPolicyError("local model actual usage exceeded its admitted budget") from exc
        except BaseException as exc:
            if dispatched.is_set():
                _quarantine_provider_usage(
                    self.admission_runtime, lease, reason="local-dispatch-or-response-ambiguous"
                )
            else:
                _release_provider_lease(self.admission_runtime, lease)
            if isinstance(exc, LocalInferenceCancelled):
                raise ProviderInvocationError("local model deadline exceeded or execution cancelled") from exc
            if isinstance(exc, ProviderPolicyError):
                raise ProviderPolicyError("local model admission denied: " + str(exc)) from exc
            raise
        finally:
            _LOCAL_DISPATCH_OBSERVER.reset(observer)
        actual = _actual_provider_usage(
            response,
            estimate=estimate,
            wall_seconds=time.perf_counter() - started,
            attempts_used=1,
            normalized_usage=response.usage,
        )
        completion = complete_usage(actual.input_tokens, actual.output_tokens)
        if completion.operation_overrun:
            raise ProviderPolicyError("local model actual usage exceeded its admitted budget")
        return replace(
            response,
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
        )


class _UnavailableLocalAdapter(ProviderAdapter):
    """Startup diagnostics only; this descriptor cannot perform inference."""

    provider_id = "local"
    model = None

    def __init__(self, readiness_code: str) -> None:
        self.readiness_code = readiness_code

    @property
    def available(self) -> bool:
        return False

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise ProviderUnavailableError("local provider is not activated")


class ProviderRegistry:
    """Configuration-driven provider selector with mandatory architecture read."""

    def __init__(
        self,
        adapters: Sequence[ProviderAdapter],
        *,
        active: str,
        verification_adapter: ProviderAdapter | None = None,
        fallback_ids: Sequence[str] = (),
        architecture_loader: Callable[[str], ProviderArchitectureReceipt] = load_provider_architecture,
    ) -> None:
        normalized_adapters = tuple(adapters)
        self._adapters: dict[str, ProviderAdapter] = {}
        self._model_adapters: dict[tuple[str, str | None], ProviderAdapter] = {}
        for adapter in normalized_adapters:
            provider_id = adapter.provider_id
            model_id = getattr(adapter, "model", None)
            identity = (provider_id, model_id)
            if identity in self._model_adapters:
                raise ValueError("provider/model identities must be unique")
            if provider_id in self._adapters and provider_id != "local":
                raise ValueError("hosted provider ids must be unique")
            if provider_id == "local" and provider_id in self._adapters and (
                not isinstance(model_id, str) or not model_id or model_id != model_id.strip()
            ):
                raise ValueError("additional local models require an exact model identity")
            self._adapters.setdefault(provider_id, adapter)
            self._model_adapters[identity] = adapter
        self.active_id = active.strip().lower()
        normalized_fallbacks = tuple(str(item).strip().lower() for item in fallback_ids)
        if len(set(normalized_fallbacks)) != len(normalized_fallbacks):
            raise ValueError("fallback provider ids must be unique")
        if self.active_id in normalized_fallbacks:
            raise ValueError("active provider cannot also be a fallback")
        unknown = [provider_id for provider_id in normalized_fallbacks if provider_id not in self._adapters]
        if unknown:
            raise ValueError("fallback provider is not registered: " + ", ".join(unknown))
        self._fallback_ids = normalized_fallbacks
        self._verification_adapter = verification_adapter
        self._architecture_loader = architecture_loader
        self._architecture_receipts: dict[str, ProviderArchitectureReceipt] = {}
        self._failover_adapter: FailoverProviderAdapter | None = None

    @classmethod
    def from_env(
        cls,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        retain_unavailable: bool = False,
        guarded_components: Any | None = None,
        require_guarded_local: bool | None = None,
    ) -> ProviderRegistry:
        try:
            return cls._from_env(
                admission_runtime=admission_runtime,
                guarded_components=guarded_components,
                require_guarded_local=require_guarded_local,
            )
        except ProviderUnavailableError:
            if not retain_unavailable or os.getenv("AI_PROVIDER", "openai").strip().lower() != "local":
                raise
            model_path = os.getenv("AI_LOCAL_MODEL_PATH", "").strip()
            deployment_path = os.getenv("AI_LOCAL_DEPLOYMENT_PATH", "").strip()
            catalog_path = os.getenv("AI_LOCAL_MODEL_CATALOG_PATH", "").strip()
            if any(
                os.getenv(name, "").strip()
                for name in (
                    "AI_SECONDARY_API_KEY",
                    "AI_SECONDARY_BASE_URL",
                    "AI_SECONDARY_MODEL",
                )
            ):
                code = "local_external_fallback_denied"
            elif os.getenv("AI_VERIFICATION_MODEL", "").strip():
                code = "local_external_verifier_denied"
            elif not model_path and not deployment_path and not catalog_path:
                code = "local_model_not_configured"
            elif sum(bool(value) for value in (model_path, deployment_path, catalog_path)) != 1:
                code = "local_configuration_invalid"
            elif catalog_path:
                code = "local_catalog_invalid"
            else:
                code = "local_artifact_invalid"
            return cls([_UnavailableLocalAdapter(code)], active="local")

    @classmethod
    def _from_env(
        cls,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        guarded_components: Any | None = None,
        require_guarded_local: bool | None = None,
    ) -> ProviderRegistry:
        active = os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai"
        if guarded_components is not None:
            from skeleton.ai.runtime.inference.guarded_composition import ProtectedLocalComponents

            if active != "local":
                raise ProviderPolicyError("protected local components require a trusted local provider")
            if not isinstance(guarded_components, ProtectedLocalComponents):
                raise ProviderUnavailableError("local guarded inference requires trusted dependencies")
        timeout = _env_float("AI_TIMEOUT_SECONDS", 45.0, minimum=1.0)
        retries = _env_int("AI_MAX_RETRIES", 2, minimum=0)
        secondary_values = {
            "api_key": os.getenv("AI_SECONDARY_API_KEY", "").strip(),
            "base_url": os.getenv("AI_SECONDARY_BASE_URL", "").strip(),
            "model": os.getenv("AI_SECONDARY_MODEL", "").strip(),
        }
        verification_model = os.getenv(
            "AI_VERIFICATION_MODEL",
            "",
        ).strip()
        catalog_path = os.getenv("AI_LOCAL_MODEL_CATALOG_PATH", "").strip()
        if catalog_path and active != "local":
            raise ProviderUnavailableError("local model catalogs require AI_PROVIDER=local")

        if active == "local":
            # Environment variables alone cannot authorize disabling guarded inference.
            guard_policy = os.getenv("AI_LOCAL_GUARD_REQUIRED", "1").strip().lower()
            if guard_policy not in {"0", "1", "false", "true"}:
                raise ProviderUnavailableError("invalid AI_LOCAL_GUARD_REQUIRED policy")
            opt_out_requested = guard_policy in {"0", "false"}
            if opt_out_requested:
                if (
                    require_guarded_local is not False
                    or os.getenv("AI_DEPLOYMENT_ENV", "").strip().lower() != "development"
                    or os.getenv("AI_LOCAL_LEGACY_DEV_ACK", "").strip() != "unsafe-local-dev-only"
                ):
                    raise ProviderUnavailableError(
                        "development-only local guard opt-out requires trusted caller authorization"
                    )
            elif guarded_components is None:
                raise ProviderUnavailableError("local guarded inference requires trusted dependencies")
            if any(secondary_values.values()):
                raise ProviderUnavailableError(
                    "local provider mode forbids secondary external provider configuration"
                )
            if verification_model:
                raise ProviderUnavailableError("local provider mode forbids semantic verifier configuration")
            model_path = os.getenv("AI_LOCAL_MODEL_PATH", "").strip()
            deployment_path = os.getenv("AI_LOCAL_DEPLOYMENT_PATH", "").strip()
            if sum(bool(value) for value in (model_path, deployment_path, catalog_path)) != 1:
                raise ProviderUnavailableError(
                    "local provider requires exactly one artifact, deployment manifest or model catalog"
                )
            capacity = _local_execution_capacity()
            cache_size, default_seed = _local_model_configuration(
                default_cache_size=0 if catalog_path or deployment_path else 128
            )
            local_admission = admission_runtime or AdmissionRuntime()
            require_guarded_inference = not opt_out_requested or guarded_components is not None

            def guarded(adapter: ProviderAdapter) -> ProviderAdapter:
                return _GovernedLocalAdapter(
                    adapter, admission_runtime=local_admission, timeout_seconds=timeout
                )

            if catalog_path:
                try:
                    from skeleton.ai.runtime.inference.catalog import LocalModelCatalogError, load_local_model_catalog

                    activation = load_local_model_catalog(
                        catalog_path,
                        cache_size=cache_size,
                        default_seed=default_seed,
                        require_guarded_inference=require_guarded_inference,
                        guarded_components=guarded_components,
                        **capacity,
                    )
                except (LocalModelCatalogError, OSError, TypeError, ValueError) as exc:
                    raise ProviderUnavailableError("local provider catalog failed activation") from exc
                configured = {id(adapter): guarded(adapter) for adapter in activation.adapters}
                return cls(
                    tuple(configured.values()),
                    active="local",
                    verification_adapter=(
                        None
                        if activation.verification_adapter is None
                        else configured[id(activation.verification_adapter)]
                    ),
                )
            if deployment_path:
                try:
                    from skeleton.ai.runtime.inference.deployment import (
                        LocalModelDeploymentError,
                        load_local_model_adapter,
                    )

                    adapter = load_local_model_adapter(
                        deployment_path,
                        cache_size=cache_size,
                        default_seed=default_seed,
                        rehash_artifacts_each_run=True,
                        require_guarded_inference=require_guarded_inference,
                        guarded_components=guarded_components,
                        **capacity,
                    )
                except (LocalModelDeploymentError, OSError, TypeError, ValueError) as exc:
                    raise ProviderUnavailableError("local provider deployment failed activation") from exc
                return cls([guarded(adapter)], active="local")
            try:
                from skeleton.ai.runtime.inference import (
                    LocalInferenceEngine,
                    LocalModelAdapter,
                    LocalModelArtifactError,
                    load_local_model_artifact,
                )

                loaded = load_local_model_artifact(model_path)
                engine = LocalInferenceEngine(
                    loaded.model,
                    cache_size=cache_size,
                    require_guarded_context=require_guarded_inference,
                    **capacity,
                )
                if require_guarded_inference:
                    from skeleton.ai.runtime.inference.guarded_composition import compose_protected_local_adapter

                    local_adapter = compose_protected_local_adapter(
                        engine,
                        components=guarded_components,
                        default_seed=default_seed,
                        artifact_status=loaded.receipt.as_dict(),
                    )
                else:
                    local_adapter = LocalModelAdapter(
                        engine,
                        default_seed=default_seed,
                        artifact_status=loaded.receipt.as_dict(),
                    )
            except (LocalModelArtifactError, TypeError, ValueError) as exc:
                raise ProviderUnavailableError("local provider model artifact failed activation") from exc
            return cls(
                [guarded(local_adapter)],
                active="local",
            )

        adapter = OpenAIProviderAdapter(
            timeout_seconds=timeout,
            max_retries=retries,
            admission_runtime=admission_runtime,
        )
        adapters: list[ProviderAdapter] = [adapter]
        fallback_ids: tuple[str, ...] = ()

        configured_secondary = any(secondary_values.values())
        if configured_secondary:
            missing = [key for key, value in secondary_values.items() if not value]
            if missing:
                raise ProviderUnavailableError(
                    "secondary provider configuration is incomplete: " + ", ".join(sorted(missing))
                )
            secondary_url = _validate_provider_base_url(secondary_values["base_url"])
            primary_url = _validate_provider_base_url(adapter.base_url or _DEFAULT_OPENAI_BASE_URL)
            if (urlsplit(secondary_url).hostname or "").rstrip(".").lower() == (
                urlsplit(primary_url).hostname or ""
            ).rstrip(".").lower():
                raise ProviderUnavailableError("secondary provider must use a distinct provider hostname")
            secondary = OpenAICompatibleSecondaryAdapter(
                api_key=secondary_values["api_key"],
                model=secondary_values["model"],
                base_url=secondary_url,
                timeout_seconds=timeout,
                max_retries=retries,
                admission_runtime=admission_runtime,
            )
            adapters.append(secondary)
            if active == secondary.provider_id:
                fallback_ids = (adapter.provider_id,)
            else:
                fallback_ids = (secondary.provider_id,)

        verification_adapter = None
        if verification_model and verification_model != adapter.model:
            verification_adapter = OpenAIProviderAdapter(
                api_key=adapter.api_key,
                model=verification_model,
                base_url=adapter.base_url,
                timeout_seconds=timeout,
                max_retries=retries,
                admission_runtime=admission_runtime,
            )
        return cls(
            adapters,
            active=active,
            verification_adapter=verification_adapter,
            fallback_ids=fallback_ids,
        )

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
        if adapter is None:
            return False
        candidate_ids = (self.active_id, *self._fallback_ids)
        try:
            for provider_id in candidate_ids:
                self._architecture_receipt(provider_id)
        except ProviderUnavailableError:
            return False
        return any(self._adapters[provider_id].available for provider_id in candidate_ids)

    def require_selected(self, provider_id: str, model_id: str) -> ProviderAdapter:
        """Select exactly one configured, architecture-acknowledged model.

        An explicit user selection cannot silently fall back to a different
        provider or model, even when the automatic route has fallbacks.
        """
        if (
            not isinstance(provider_id, str)
            or not provider_id
            or provider_id != provider_id.strip()
            or not isinstance(model_id, str)
            or not model_id
            or model_id != model_id.strip()
        ):
            raise ProviderUnavailableError("explicit provider selection is malformed")
        adapter = self._model_adapters.get((provider_id, model_id))
        if adapter is None or getattr(adapter, "model", None) != model_id:
            raise ProviderUnavailableError("selected provider/model is not configured")
        self._architecture_receipt(provider_id)
        if not adapter.available:
            raise ProviderUnavailableError("selected provider/model is unavailable")
        return adapter

    def require_active(self) -> ProviderAdapter:
        adapter = self.active
        if adapter is None:
            raise ProviderUnavailableError(f"unsupported AI provider: {self.active_id}")
        self._architecture_receipt(self.active_id)
        fallbacks: list[ProviderAdapter] = []
        for provider_id in self._fallback_ids:
            self._architecture_receipt(provider_id)
            fallbacks.append(self._adapters[provider_id])

        if fallbacks:
            if self._failover_adapter is None:
                self._failover_adapter = FailoverProviderAdapter(
                    adapter,
                    tuple(fallbacks),
                )
            if not self._failover_adapter.available:
                raise ProviderUnavailableError("no declared AI provider is configured")
            return self._failover_adapter

        if not adapter.available:
            raise ProviderUnavailableError(f"AI provider is not configured: {self.active_id}")
        return adapter

    def require_for_context(self, context_policy: Mapping[str, Any]) -> ProviderAdapter:
        """Resolve an immutable exact selection without changing fallback policy."""
        selection = provider_context_selection(context_policy)
        if selection is None:
            adapter = self.require_active()
            candidates = (self.active_id, *self._fallback_ids)
            model = getattr(self.active, "model", None)
        else:
            provider_id, model = selection["provider_id"], selection["model_id"]
            adapter = self.require_selected(provider_id, model)
            candidates = (provider_id,)
        legacy_model = context_policy.get("provider_model")
        if legacy_model is not None and legacy_model != model:
            raise ProviderUnavailableError("model override differs from configured selection")
        temperature = provider_context_temperature(context_policy)
        if temperature is not None and any(
            provider_id == "local"
            or not _supports_temperature(getattr(self._adapters[provider_id], "model", None))
            for provider_id in candidates
        ):
            raise ProviderUnavailableError("model route does not support temperature")
        return adapter

    def redundancy_status(self) -> dict[str, Any]:
        routing = self._failover_adapter.routing_snapshot() if self._failover_adapter is not None else None
        return {
            "enabled": bool(self._fallback_ids),
            "primary_provider": self.active_id,
            "fallback_providers": list(self._fallback_ids),
            "routing": routing,
        }

    def runtime_serving_engines(self) -> tuple[Any, ...]:
        """Return registered local serving owners, without activating a route.

        Runtime pressure and maintenance never create a provider, resolve
        credentials, change a selected model or alter activation identity.
        Shared engines are returned once even when several adapters use them.
        A separately supplied local verifier is also an activated owner, even
        when it is intentionally absent from selectable generation routes.
        """
        engines: list[Any] = []
        seen: set[int] = set()
        for adapter in (*self._model_adapters.values(), self._verification_adapter):
            if adapter is None or adapter.provider_id != "local":
                continue
            engine = getattr(adapter, "engine", None)
            if (
                engine is not None
                and id(engine) not in seen
                and callable(getattr(engine, "configure_serving", None))
                and callable(getattr(engine, "maintain", None))
            ):
                engines.append(engine)
                seen.add(id(engine))
        return tuple(engines)

    def runtime_serving_routes(self) -> tuple[dict[str, Any], ...]:
        """Name each local serving owner by its configured exact route identity."""

        routes: list[dict[str, Any]] = []
        for (provider_id, model_id), adapter in sorted(
            self._model_adapters.items(), key=lambda item: (item[0][0], item[0][1] or "")
        ):
            engine = getattr(adapter, "engine", None)
            if (
                provider_id == "local"
                and isinstance(model_id, str)
                and engine is not None
                and callable(getattr(engine, "configure_serving", None))
                and callable(getattr(engine, "maintain", None))
            ):
                routes.append({
                    "route_id": provider_id + ":" + model_id,
                    "provider_id": provider_id,
                    "model_id": model_id,
                    "model_digest": getattr(getattr(engine, "model", None), "model_digest", None),
                    "engine": engine,
                })
        return tuple(routes)

    def verification_adapter_for(
        self,
        generator: ProviderAdapter,
    ) -> ProviderAdapter | None:
        """Return a separately configured semantic verifier or fail closed.

        The verifier must differ from the generator by provider or model. This
        prevents the production coordinator from silently calling the same
        model instance an independent verifier.
        """

        adapter = self._verification_adapter
        if adapter is None:
            return None
        if not isinstance(generator, ProviderAdapter):
            raise TypeError("generator must implement ProviderAdapter")
        if not adapter.available:
            return None
        self._architecture_receipt(adapter.provider_id)
        return adapter if self._independent_models(generator, adapter) else None

    @staticmethod
    def _independent_models(generator: ProviderAdapter, verifier: ProviderAdapter) -> bool:
        if (generator.provider_id, getattr(generator, "model", None)) == (
            verifier.provider_id, getattr(verifier, "model", None),
        ):
            return False
        if generator.provider_id == verifier.provider_id == "local":
            digests = [
                getattr(getattr(getattr(adapter, "engine", None), "model", None), "model_digest", None)
                for adapter in (generator, verifier)
            ]
            if any(
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                for digest in digests
            ):
                return False
            return digests[0] != digests[1]
        return True

    def architecture_receipt(self, provider_id: str | None = None) -> dict[str, Any]:
        target = (provider_id or self.active_id).strip().lower()
        if target not in self._adapters:
            raise ProviderUnavailableError(f"unsupported AI provider: {target}")
        return self._architecture_receipt(target).as_dict()

    def statuses(self) -> list[dict[str, Any]]:
        statuses = []
        for (provider_id, _model_id), adapter in sorted(
            self._model_adapters.items(), key=lambda item: (item[0][0], item[0][1] or "")
        ):
            local = provider_id == "local"
            try:
                status = adapter.status()
            except (OSError, ValueError, RuntimeError):
                if not local:
                    raise
                # Health/model discovery remains readable after local weight
                # drift; the affected route is explicitly unavailable.
                status = {
                    "id": provider_id,
                    "model": getattr(adapter, "model", None),
                    "available": False,
                    "readiness_code": "local_artifact_identity_invalid",
                }
            context_window = 16_384 if local else 128_000
            tokenizer = "approximate_text"
            output_limit = 8_192 if local else 16_384
            limits_source = "engine_chat_policy"
            if local:
                limits = status.get("generation_limits")
                if isinstance(limits, Mapping):
                    context_window = limits["context_window"]
                    output_limit = limits["max_output_tokens"]
                    tokenizer = limits["tokenizer"]
                    limits_source = limits["limits_source"]
                else:
                    tokenizer = "utf8_bytes_upper_bound"
            protocols = status.get("protocol_capabilities", ["text-generation"])
            status.update(
                {
                    "configured": (
                        not isinstance(adapter, _UnavailableLocalAdapter)
                        if local
                        else bool(getattr(adapter, "api_key", None) or getattr(adapter, "_client", None))
                    ),
                    "credential_free": local,
                    "execution_mode": "local" if local else "hosted",
                    "capabilities": list(protocols),
                    "context_window": context_window,
                    "max_output_tokens": output_limit,
                    "default_output_tokens": (
                        min(256, output_limit, max(1, context_window // 4)) if local else 4_096
                    ),
                    "limits_source": limits_source,
                    "tokenizer": tokenizer,
                    "supports_temperature": not local
                    and _supports_temperature(getattr(adapter, "model", None)),
                    "readiness_code": (
                        "ready"
                        if status["available"]
                        else status.get("readiness_code")
                        or getattr(
                            adapter,
                            "readiness_code",
                            (
                                "local_model_unavailable"
                                if local
                                else (
                                    "provider_credentials_missing"
                                    if not getattr(adapter, "api_key", None)
                                    else "provider_configuration_unavailable"
                                )
                            ),
                        )
                    ),
                }
            )
            status["active"] = adapter is self.active
            status["fallback"] = provider_id in self._fallback_ids and adapter is self._adapters[provider_id]
            status["routing"] = (
                self.redundancy_status() if provider_id == self.active_id and self._fallback_ids else None
            )
            verifier = self._verification_adapter
            status["semantic_verifier_configured"] = bool(
                verifier is not None
                and verifier.provider_id == provider_id
                and self._independent_models(adapter, verifier)
            )
            status["semantic_verifier_route"] = adapter is verifier
            try:
                receipt = self._architecture_receipt(provider_id)
            except ProviderUnavailableError:
                status["available"] = False
                status["readiness_code"] = "provider_architecture_unacknowledged"
                status["architecture_acknowledged"] = False
                status["architecture_tag"] = None
                status["construction_version"] = None
            else:
                status["architecture_acknowledged"] = True
                status["architecture_tag"] = receipt.architecture_tag
                status["construction_version"] = receipt.construction_version
            statuses.append(status)
        return statuses


def _execution_binding_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(encoded) > 65536:
        raise ProviderPolicyError("provider execution identity exceeds its bound")
    return hashlib.sha256(encoded).hexdigest()


def _execution_source_identity() -> dict[str, object]:
    spec = find_spec("skeleton")
    if spec is None or spec.origin is None:
        raise ProviderPolicyError("canonical provider source identity is unavailable")
    root = Path(spec.origin).parent
    paths = (
        "provider_runtime.py",
        "intelligence/execution_runtime.py",
        "intelligence/cooperation.py",
        "intelligence/verification_runtime.py",
        "intelligence/verification_policy.py",
        "ai/runtime/inference/local.py",
        "ai/runtime/inference/adaptive_serving.py",
        "ai/runtime/inference/artifact.py",
        "ai/runtime/inference/neural.py",
        "ai/runtime/inference/native_runtime.py",
        "ai/runtime/inference/native_transformer.py",
        "ai/runtime/inference/llama_cpp.py",
        "ai/runtime/inference/deployment.py",
        "ai/runtime/inference/catalog.py",
        "cortex/attn.py",
        "cortex/bpe.py",
        "cortex/transformer.py",
    )
    try:
        native_sources = tuple(
            path.relative_to(root).as_posix()
            for path in sorted((root / "ai/model_runtime").rglob("*.py"))
            if "__pycache__" not in path.parts
        )
        if not native_sources:
            raise OSError("canonical native model runtime sources are unavailable")
        sources = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (*paths, *native_sources)
        }
    except OSError as exc:
        raise ProviderPolicyError("canonical provider source identity is unavailable") from exc
    packages = {}
    for name in ("numpy", "openai"):
        try:
            packages[name] = package_metadata.version(name)
        except package_metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "sources": sources,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "packages": packages,
    }


def provider_execution_identity(adapter: ProviderAdapter) -> dict[str, object]:
    """Pin declared routes and activation configuration without provider IO."""
    routes = (
        (adapter.primary, *adapter.fallbacks) if isinstance(adapter, FailoverProviderAdapter) else (adapter,)
    )
    if not 1 <= len(routes) <= 8:
        raise ProviderPolicyError("provider route count exceeds binding capacity")
    records = []
    seen = set()
    for route in routes:
        provider_id, model = getattr(route, "provider_id", None), getattr(route, "model", None)
        if any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > maximum
            or any(ord(char) < 32 for char in value)
            for value, maximum in ((provider_id, 128), (model, 256))
        ):
            raise ProviderPolicyError("provider route identity is invalid")
        if provider_id in seen:
            raise ProviderPolicyError("provider route identity is duplicated")
        seen.add(provider_id)
        endpoint = getattr(route, "base_url", None)
        if endpoint is not None and (not isinstance(endpoint, str) or len(endpoint) > 4096):
            raise ProviderPolicyError("provider endpoint identity is invalid")
        record = {
            "provider_id": provider_id,
            "model_id": model,
            "adapter": type(route).__module__ + "." + type(route).__qualname__,
            "endpoint_digest": _execution_binding_digest(endpoint),
            "timeout_seconds": getattr(route, "timeout_seconds", None),
            "max_retries": getattr(route, "max_retries", None),
        }
        if provider_id in {"openai", "openai-compatible-secondary", "local"}:
            receipt = load_provider_architecture(provider_id)
            record["architecture"] = {
                "architecture_tag": receipt.architecture_tag,
                "construction_version": receipt.construction_version,
                "contract_digest": receipt.contract_digest,
                "provider_family": receipt.provider_family,
            }
        if provider_id == "local":
            status = route.status()
            artifact = status.get("artifact") or {}
            model_digest = status.get("model_digest")
            from skeleton.ai.runtime.inference.local import ReferenceNGramModel
            from skeleton.ai.runtime.inference.local import _digest as reference_digest

            local_model = getattr(getattr(route, "engine", None), "model", None)
            if (
                isinstance(local_model, ReferenceNGramModel)
                and reference_digest(local_model.to_dict(include_digest=False)) != model_digest
            ):
                raise ProviderPolicyError("local reference content changed behind its claimed digest")
            if (
                not isinstance(model_digest, str)
                or len(model_digest) != 64
                or any(char not in "0123456789abcdef" for char in model_digest)
            ):
                raise ProviderPolicyError("local model activation digest is invalid")
            activation = {
                "model_digest": model_digest,
                "runtime_digest": status.get("runtime_digest"),
                "execution_profile_digest": status.get("execution_profile_digest"),
                "artifact": {
                    name: artifact.get(name)
                    for name in (
                        "schema",
                        "model_id",
                        "model_digest",
                        "artifact_sha256",
                        "runtime_digest",
                        "manifest_digest",
                        "source_model_id",
                        "catalog_digest",
                        "catalog_entry_digest",
                        "catalog_source_sha256",
                    )
                },
                "default_seed": getattr(route, "default_seed", None),
                "capacity": status.get("capacity"),
                "protocol_capabilities": status.get("protocol_capabilities"),
                "generation_limits": status.get("generation_limits"),
            }
            for name in ("runtime_digest", "execution_profile_digest"):
                value = activation[name]
                if value is not None and (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)
                ):
                    raise ProviderPolicyError("local activation runtime digest is invalid")
            record["local_activation"] = activation
        _execution_binding_digest(record)
        records.append(record)
    identity = {
        "schema_version": "skeleton.provider.route_binding.v1",
        "mode": "declared_failover" if isinstance(adapter, FailoverProviderAdapter) else "single",
        "routes": records,
        "runtime": _execution_source_identity(),
    }
    identity["identity_digest"] = _execution_binding_digest(identity)
    return identity


def provider_response_matches_identity(
    identity: Mapping[str, object], provider_id: object, model_id: object
) -> bool:
    """A response may identify only an exact configured declared route pair."""
    if (
        not isinstance(identity, Mapping)
        or identity.get("schema_version") != "skeleton.provider.route_binding.v1"
    ):
        return False
    unsigned = {key: value for key, value in identity.items() if key != "identity_digest"}
    if identity.get("identity_digest") != _execution_binding_digest(unsigned):
        return False
    routes = identity.get("routes")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 8:
        return False
    return any(
        isinstance(route, Mapping)
        and route.get("provider_id") == provider_id
        and route.get("model_id") == model_id
        for route in routes
    )


def _local_execution_capacity() -> dict[str, int]:
    """Operator-only fixed admission limits; invalid configuration fails closed."""
    resolved = {}
    for key, name, default, minimum, maximum in (
        ("max_concurrency", "AI_LOCAL_MODEL_MAX_CONCURRENCY", 1, 1, 32),
        ("max_queue_size", "AI_LOCAL_MODEL_MAX_QUEUE_SIZE", 256, 0, 65536),
        ("max_batch_size", "AI_LOCAL_MODEL_MAX_BATCH_SIZE", 256, 1, 4096),
    ):
        raw = os.getenv(name)
        try:
            value = default if raw is None else int(raw)
        except ValueError as exc:
            raise ProviderUnavailableError("local provider capacity configuration is invalid") from exc
        if not minimum <= value <= maximum:
            raise ProviderUnavailableError("local provider capacity configuration is out of bounds")
        resolved[key] = value
    return resolved


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ProviderUnavailableError(name + " must be finite numeric within configured bounds") from exc
    if not math.isfinite(value) or value < minimum:
        raise ProviderUnavailableError(name + " is outside configured bounds")
    return value


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderUnavailableError(name + " must be an integer within configured bounds") from exc
    if value < minimum:
        raise ProviderUnavailableError(name + " is outside configured bounds")
    return value


def _local_model_configuration(*, default_cache_size: int) -> tuple[int, int]:
    cache = _env_int("AI_LOCAL_MODEL_CACHE_SIZE", default_cache_size, minimum=0)
    seed = _env_int("AI_LOCAL_MODEL_SEED", 0, minimum=0)
    if cache > 4096 or seed > 2**64 - 1:
        raise ProviderUnavailableError("local model cache or seed is outside configured bounds")
    return cache, seed


__all__ = [
    "AIMessage",
    "FailoverProviderAdapter",
    "FinishReason",
    "OpenAICompatibleSecondaryAdapter",
    "OpenAIProviderAdapter",
    "OpenAISyncProviderAdapter",
    "ProviderAdapter",
    "ProviderDelta",
    "ProviderDeltaKind",
    "ProviderError",
    "ProviderImageRequest",
    "ProviderImageResponse",
    "ProviderInvocationError",
    "ProviderPolicyError",
    "ProviderProtocolViolationError",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderRoutingTelemetry",
    "ProviderSpeechRequest",
    "ProviderSpeechResponse",
    "ProviderStructuredOutput",
    "ProviderToolCall",
    "ProviderToolDefinition",
    "ProviderUnavailableError",
    "ProviderUsage",
    "normalize_history",
    "provider_context_selection",
    "provider_context_temperature",
    "provider_execution_identity",
    "provider_request_from_context",
    "provider_response_deltas",
    "provider_response_matches_identity",
    "require_provider_response_context",
]
