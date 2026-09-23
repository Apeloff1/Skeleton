"""Canonical AI model-provider runtime for the Skeleton engine.

Provider-specific SDK objects, credentials, governance/admission checks, and
provider network policy live behind this engine-owned boundary. Application
code may consume these neutral contracts through compatibility facades, but it
must not create a second credential-bearing provider runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import deque
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address, ip_address
import base64
import hashlib
import inspect
import io
import json
import math
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from skeleton.contracts.context import ContextEnvelope
from skeleton.provider_contract import (
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


class ProviderPolicyError(ProviderError):
    """Raised when governance or admission denies provider-bound work."""


def _read_provider_json(response: Any) -> Mapping[str, Any]:
    """Read one provider JSON response under the canonical hard byte budget."""

    raw = response.read(_MAX_PROVIDER_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderInvocationError("model provider response exceeded size limit")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ProviderInvocationError(
            "model provider returned malformed JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ProviderInvocationError("model provider returned malformed JSON")
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
    operation_id: str | None = None
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

    async def generate_image(self, request: ProviderImageRequest) -> ProviderImageResponse:
        raise ProviderUnavailableError(
            f"provider does not implement image generation: {self.provider_id}"
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
    ) -> ProviderImageResponse:
        del image, count, size, data_class, tenant_id, operation_id
        raise ProviderUnavailableError(
            f"provider does not implement image variation: {self.provider_id}"
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
    ) -> ProviderImageResponse:
        del image, prompt, mask, size, data_class, tenant_id, operation_id
        raise ProviderUnavailableError(
            f"provider does not implement image editing: {self.provider_id}"
        )

    async def synthesize_speech(
        self, request: ProviderSpeechRequest
    ) -> ProviderSpeechResponse:
        raise ProviderUnavailableError(
            f"provider does not implement speech synthesis: {self.provider_id}"
        )


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
            raise ProviderPolicyError(
                "model provider tools must contain ProviderToolDefinition values"
            )
        add(definition)

    for raw in request.tool_schemas:
        schema = _strict_json_object(raw, "model provider tool schema")
        try:
            if (
                isinstance(schema.get("tool_id"), str)
                and isinstance(schema.get("input_schema"), Mapping)
            ):
                definition = ProviderToolDefinition(
                    tool_id=schema["tool_id"],
                    description=str(schema.get("description") or schema["tool_id"]),
                    input_schema=dict(schema["input_schema"]),
                )
            elif schema.get("type") == "function" and isinstance(
                schema.get("function"), Mapping
            ):
                function = dict(schema["function"])
                definition = ProviderToolDefinition(
                    tool_id=str(function.get("name") or ""),
                    description=str(
                        function.get("description")
                        or function.get("name")
                        or ""
                    ),
                    input_schema=dict(function.get("parameters") or {}),
                )
            elif schema.get("type") == "function":
                definition = ProviderToolDefinition(
                    tool_id=str(schema.get("name") or ""),
                    description=str(
                        schema.get("description") or schema.get("name") or ""
                    ),
                    input_schema=dict(schema.get("parameters") or {}),
                )
            else:
                raise ProviderProtocolError("unsupported provider tool schema")
        except (ProviderProtocolError, TypeError, ValueError) as exc:
            raise ProviderPolicyError(
                "model provider tool schema cannot be normalized"
            ) from exc
        add(definition)

    if len(definitions) > 256:
        raise ProviderPolicyError("model provider tool count exceeds protocol limit")
    return tuple(definitions[key] for key in sorted(definitions))


def _provider_tool_payloads(
    request: ProviderRequest,
) -> list[dict[str, Any]]:
    return [
        definition.as_openai_tool()
        for definition in _provider_tool_definitions(request)
    ]


def _provider_tool_choice_payload(
    request: ProviderRequest,
    tools: tuple[ProviderToolDefinition, ...],
) -> object | None:
    choice = str(request.tool_choice or "auto").strip().lower()
    if choice not in {"none", "auto", "required", "specific"}:
        raise ProviderPolicyError("model provider tool_choice is invalid")
    offered = {tool.tool_id for tool in tools}
    if not offered:
        if choice in {"required", "specific"}:
            raise ProviderPolicyError(
                "model provider tool_choice requires offered tools"
            )
        return "none"
    if choice == "specific":
        tool_id = str(request.specific_tool_id or "").strip()
        if not tool_id or tool_id not in offered:
            raise ProviderPolicyError(
                "specific provider tool choice must reference an offered tool"
            )
        return {"type": "function", "name": tool_id}
    if request.specific_tool_id is not None:
        raise ProviderPolicyError(
            "specific_tool_id requires tool_choice='specific'"
        )
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


def _remaining_provider_timeout(
    request: ProviderRequest,
    configured_timeout: float,
) -> float:
    timeout = float(configured_timeout)
    if request.deadline is None:
        return timeout
    deadline = request.deadline
    if (
        not isinstance(deadline, datetime)
        or deadline.tzinfo is None
        or deadline.utcoffset() is None
    ):
        raise ProviderPolicyError("model provider deadline must be timezone-aware")
    remaining = (
        deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining <= 0:
        raise ProviderInvocationError("model provider deadline exceeded")
    return max(0.001, min(timeout, remaining))


def _provider_field(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _provider_output_items(response: object) -> tuple[object, ...]:
    output = _provider_field(response, "output", ())
    if output is None:
        return ()
    if isinstance(output, SequenceABC) and not isinstance(
        output, (str, bytes, bytearray)
    ):
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
    call_id = str(
        _provider_field(item, "call_id", None)
        or _provider_field(item, "id", None)
        or ""
    ).strip()
    tool_id = str(
        _provider_field(item, "name", None)
        or _provider_field(item, "tool_id", None)
        or ""
    ).strip()
    if not call_id or not tool_id:
        raise ProviderInvocationError(
            "model provider returned malformed tool call"
        )
    if tool_id not in offered_tool_ids:
        raise ProviderInvocationError(
            "model provider returned an unoffered tool call"
        )
    raw_arguments = _provider_field(item, "arguments", {})
    if isinstance(raw_arguments, str):
        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ProviderInvocationError(
                "model provider returned malformed tool arguments"
            ) from exc
    else:
        parsed_arguments = raw_arguments
    if not isinstance(parsed_arguments, Mapping):
        raise ProviderInvocationError(
            "model provider tool arguments must be a JSON object"
        )
    try:
        return ProviderToolCall(
            call_id=call_id,
            tool_id=tool_id,
            arguments=dict(parsed_arguments),
        )
    except ProviderProtocolError as exc:
        raise ProviderInvocationError(
            "model provider returned invalid normalized tool call"
        ) from exc


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
            raise ProviderInvocationError(
                "model provider returned duplicate tool call id"
            )
        seen.add(call.call_id)
        calls.append(call)
        if len(calls) > 256:
            raise ProviderInvocationError(
                "model provider returned too many tool calls"
            )
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
            raise ProviderInvocationError(
                "model provider structured output is not an object"
            )
        return _strict_json_object(
            parsed,
            "model provider structured output",
        )
    if requested_schema is None or not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderInvocationError(
            "model provider structured output is invalid JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise ProviderInvocationError(
            "model provider structured output is not an object"
        )
    return _strict_json_object(
        value,
        "model provider structured output",
    )


def _normalized_provider_usage(
    response: object,
    *,
    estimated_cost_usd: float,
) -> ProviderUsage:
    usage = _provider_field(response, "usage", None)
    if usage is None:
        source = "estimate"
        input_tokens = output_tokens = cached_tokens = reasoning_tokens = total = None
    else:
        source = "provider"
        input_tokens = _provider_field(usage, "input_tokens", None)
        output_tokens = _provider_field(usage, "output_tokens", None)
        total = _provider_field(usage, "total_tokens", None)
        input_details = _provider_field(usage, "input_tokens_details", None)
        output_details = _provider_field(usage, "output_tokens_details", None)
        cached_tokens = (
            _provider_field(input_details, "cached_tokens", None)
            if input_details is not None
            else None
        )
        reasoning_tokens = (
            _provider_field(output_details, "reasoning_tokens", None)
            if output_details is not None
            else None
        )

    def token(value: object) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    estimated = (
        format(float(estimated_cost_usd), ".12g")
        if float(estimated_cost_usd) > 0
        else None
    )
    try:
        return ProviderUsage(
            input_tokens=token(input_tokens),
            output_tokens=token(output_tokens),
            cached_input_tokens=token(cached_tokens),
            reasoning_tokens=token(reasoning_tokens),
            total_tokens=token(total),
            estimated_cost=estimated,
            billed_cost=None,
            currency="USD" if estimated is not None else None,
            usage_source=source,
        )
    except ProviderProtocolError as exc:
        raise ProviderInvocationError(
            "model provider returned invalid usage metadata"
        ) from exc


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
        if isinstance(content, SequenceABC) and not isinstance(
            content, (str, bytes, bytearray)
        ):
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
    usage = _normalized_provider_usage(
        response,
        estimated_cost_usd=request.estimated_cost_usd,
    )
    normalized_text = text.strip() if isinstance(text, str) else None
    if normalized_text == "":
        normalized_text = None
    if normalized_text is None and structured is None and not tool_calls:
        if finish not in {
            FinishReason.REFUSAL,
            FinishReason.CONTENT_FILTERED,
            FinishReason.CANCELLED,
            FinishReason.DEADLINE,
        }:
            raise ProviderInvocationError(
                "model provider returned no normalized output"
            )
    return normalized_text, structured, tool_calls, finish, usage


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
        raise ProviderPolicyError(
            "provider purpose does not match governance context"
        )
    if tenant_id is not None and tenant_id.strip() != governance_context.tenant_id:
        raise ProviderPolicyError(
            "provider tenant does not match governance context"
        )

    return (
        governance_context.data_class.label,
        governance_context.purpose,
        governance_context.tenant_id,
    )


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
        if identity is not None and (
            not isinstance(identity, str) or not identity.strip()
        ):
            raise ProviderPolicyError(
                f"model provider {identity_name} is invalid"
            )
    if (request.context_id is None) != (request.context_digest is None):
        raise ProviderPolicyError(
            "model provider context_id and context_digest must be supplied together"
        )
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
            raise ProviderPolicyError(
                "compiled provider context requires immutable source snapshot"
            )
        seen_snapshot_ids: set[str] = set()
        previous_snapshot_id: str | None = None
        for item in request.context_source_snapshot:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ProviderPolicyError(
                    "model provider context snapshot entries must be pairs"
                )
            segment_id, content_digest = item
            try:
                parsed_segment_id = UUID(segment_id)
            except (ValueError, AttributeError) as exc:
                raise ProviderPolicyError(
                    "model provider context snapshot segment identity is invalid"
                ) from exc
            if str(parsed_segment_id) != segment_id:
                raise ProviderPolicyError(
                    "model provider context snapshot segment identity is invalid"
                )
            if segment_id in seen_snapshot_ids:
                raise ProviderPolicyError(
                    "model provider context snapshot contains duplicate segment"
                )
            if previous_snapshot_id is not None and segment_id < previous_snapshot_id:
                raise ProviderPolicyError(
                    "model provider context snapshot must be deterministically ordered"
                )
            seen_snapshot_ids.add(segment_id)
            previous_snapshot_id = segment_id
            if (
                not isinstance(content_digest, str)
                or len(content_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in content_digest)
            ):
                raise ProviderPolicyError(
                    "model provider context snapshot digest is invalid"
                )
        if (
            not isinstance(request.context_compiler_version, str)
            or not request.context_compiler_version.strip()
        ):
            raise ProviderPolicyError(
                "compiled provider context requires compiler version"
            )
    elif request.context_source_snapshot or request.context_compiler_version is not None:
        raise ProviderPolicyError(
            "context snapshot/compiler version require context identity and digest"
        )
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
            raise ProviderPolicyError(
                "context segment purpose does not match provider request purpose"
            )

    from skeleton.context.compiler import project_provider_context

    projection = project_provider_context(envelope)
    if not projection.prompt.strip():
        raise ProviderInvocationError(
            "compiled context requires a final canonical user message"
        )

    reserved_output = envelope.budget.reserved_output_tokens
    requested_output = reserved_output if max_output_tokens is None else max_output_tokens
    if (
        isinstance(requested_output, bool)
        or not isinstance(requested_output, int)
        or requested_output <= 0
    ):
        raise ProviderPolicyError(
            "compiled context requires a positive provider output reservation"
        )
    if requested_output > reserved_output:
        raise ProviderPolicyError(
            "provider output request exceeds context output reservation"
        )

    if resource_budget is None:
        resource_budget = ResourceBudget(
            max_input_tokens=envelope.budget.max_context_tokens,
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
            raise ProviderPolicyError(
                "compiled tool schema must be a non-empty JSON object"
            )
        try:
            parsed_tools.append(
                ProviderToolDefinition(
                    tool_id=str(schema.get("tool_id") or ""),
                    description=str(
                        schema.get("description")
                        or schema.get("tool_id")
                        or ""
                    ),
                    input_schema=dict(schema.get("input_schema") or {}),
                )
            )
        except (ProviderProtocolError, TypeError, ValueError) as exc:
            raise ProviderPolicyError(
                "compiled tool schema cannot become provider tool definition"
            ) from exc

    request = ProviderRequest(
        instructions=projection.instructions,
        prompt=projection.prompt,
        history=tuple(
            AIMessage(role=item["role"], content=item["content"])
            for item in projection.history
        ),
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
    input_capacity = envelope.budget.input_capacity(
        tools_enabled=bool(_provider_tool_definitions(request))
    )
    if projected_tokens > input_capacity:
        raise ProviderPolicyError(
            "provider projection exceeds compiled context input capacity"
        )
    return request


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
    """Use canonical operation identity when present, else one invocation lease ID."""

    if request.operation_id is not None:
        return request.operation_id.strip()
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
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _actual_provider_usage(
    response: object,
    *,
    estimate: UsageEstimate,
    wall_seconds: float,
    attempts_used: int = 1,
) -> UsageEstimate:
    usage = (
        response.get("usage")
        if isinstance(response, Mapping)
        else getattr(response, "usage", None)
    )
    if isinstance(usage, Mapping):
        input_value = usage.get("input_tokens")
        output_value = usage.get("output_tokens")
    else:
        input_value = getattr(usage, "input_tokens", None)
        output_value = getattr(usage, "output_tokens", None)

    return UsageEstimate(
        input_tokens=_usage_int(input_value, estimate.input_tokens),
        output_tokens=_usage_int(output_value, estimate.output_tokens),
        cost_usd=estimate.cost_usd,
        wall_seconds=max(0.0, float(wall_seconds)),
        provider_attempts=max(1, int(attempts_used)),
        tool_calls=estimate.tool_calls,
        artifact_bytes=estimate.artifact_bytes,
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
        raise ProviderPolicyError(
            "model provider request denied by resource admission"
        ) from exc
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
    if governance_context is None and (
        not isinstance(data_class, str) or not data_class.strip()
    ):
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
        raise ProviderPolicyError(
            "provider media transfer denied by governance policy"
        ) from exc

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
                operation_id=_media_operation_id(
                    provider_id, purpose, content, operation_id
                ),
                tenant_id=(tenant_id or "unbound"),
                capability=purpose,
                budget=resource_budget,
                estimate=estimate,
            )
        )
    except (AdmissionError, AdmissionRuntimeError) as exc:
        raise ProviderPolicyError(
            "provider media request denied by resource admission"
        ) from exc
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
            raise ProviderInvocationError(
                "image provider returned invalid base64 payload"
            ) from exc
        total_bytes += len(decoded)
        if total_bytes > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image provider response exceeded size limit")
        images.append(
            {
                "data": encoded,
                "format": "base64_png",
                "revised_prompt": str(
                    getattr(item, "revised_prompt", None) or fallback_prompt
                ),
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
            raise ProviderInvocationError(
                "normalized image payload is invalid"
            ) from exc
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
        effective_data_class, effective_purpose, effective_tenant_id = (
            _effective_governance_fields(
                data_class=request.data_class,
                purpose=request.purpose,
                tenant_id=request.tenant_id,
                governance_context=request.governance_context,
            )
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
            raise ProviderPolicyError(
                "model provider transfer denied by governance policy"
            ) from exc

        requested_output = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else min(4_096, request.resource_budget.max_output_tokens)
        )
        lease, estimate = _admit_provider_request(
            self.admission_runtime,
            request,
            tenant_id=effective_tenant_id,
            requested_output_tokens=requested_output,
            timeout_seconds=self.timeout_seconds,
            provider_attempts=self.max_retries + 1,
        )

        started = time.perf_counter()
        try:
            client = self._get_client()
            messages: list[dict[str, str]] = [
                message.as_openai_input() for message in request.history
            ]
            messages.append({"role": "user", "content": request.prompt})

            kwargs: dict[str, Any] = {
                "model": model,
                "instructions": request.instructions,
                "input": messages,
            }
            if request.max_output_tokens is not None:
                kwargs["max_output_tokens"] = request.max_output_tokens
            if request.tool_schemas:
                kwargs["tools"] = [dict(schema) for schema in request.tool_schemas]

            try:
                response = await client.responses.create(**kwargs)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("model provider request failed") from exc

            text = str(getattr(response, "output_text", "") or "").strip()
            if not text:
                raise ProviderInvocationError("model provider returned an empty response")
        except BaseException:
            _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _actual_provider_usage(
            response,
            estimate=estimate,
            wall_seconds=latency_seconds,
        )
        try:
            self.admission_runtime.complete(lease.operation_id, actual)
        except AdmissionRuntimeError as exc:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderPolicyError(
                "model provider usage reconciliation failed"
            ) from exc

        request_id = getattr(response, "id", None)
        return ProviderResponse(
            text=text,
            provider=self.provider_id,
            model=model,
            request_id=str(request_id) if request_id else None,
            latency_ms=round(latency_seconds * 1000, 2),
            governance_decision_id=governance.decision_id,
            admission_decision_id=lease.decision.decision_id,
            data_class=governance.data_class,
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


    async def generate_image(
        self, request: ProviderImageRequest
    ) -> ProviderImageResponse:
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ProviderInvocationError("image provider prompt must be non-empty")
        if request.count < 1 or request.count > 4:
            raise ProviderInvocationError("image provider count must be between one and four")
        if request.size not in {"256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"}:
            raise ProviderInvocationError("image provider size is unsupported")
        if request.quality not in {"standard", "hd", "low", "medium", "high", "auto"}:
            raise ProviderInvocationError("image provider quality is unsupported")

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
            timeout_seconds=self.timeout_seconds,
            provider_attempts=self.max_retries + 1,
            output_tokens=request.count,
            admission_runtime=self.admission_runtime,
        )
        started = time.perf_counter()
        try:
            client = self._get_client()
            try:
                response = await client.images.generate(
                    model=request.model,
                    prompt=request.prompt,
                    size=request.size,
                    quality=request.quality,
                    n=request.count,
                    response_format="b64_json",
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderInvocationError("image provider request failed") from exc
            images = _extract_b64_images(response, fallback_prompt=request.prompt)
        except BaseException:
            _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            self.admission_runtime.complete(lease.operation_id, actual)
        except AdmissionRuntimeError as exc:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderPolicyError(
                "image provider usage reconciliation failed"
            ) from exc

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
    ) -> ProviderImageResponse:
        if not isinstance(image, bytes) or not image:
            raise ProviderInvocationError("image variation source must be non-empty bytes")
        if len(image) > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image variation source exceeded size limit")
        if count < 1 or count > 4:
            raise ProviderInvocationError("image variation count must be between one and four")

        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose="image-variation",
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            content=image,
            estimated_cost_usd=0.0,
            resource_budget=ResourceBudget(),
            timeout_seconds=self.timeout_seconds,
            provider_attempts=self.max_retries + 1,
            output_tokens=count,
            admission_runtime=self.admission_runtime,
        )
        source = io.BytesIO(image)
        source.name = "image.png"
        started = time.perf_counter()
        try:
            client = self._get_client()
            try:
                response = await client.images.create_variation(
                    image=source,
                    n=count,
                    size=size,
                    response_format="b64_json",
                )
            except Exception as exc:
                raise ProviderInvocationError("image variation request failed") from exc
            images = _extract_b64_images(response, fallback_prompt="variation")
        except BaseException:
            _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            self.admission_runtime.complete(lease.operation_id, actual)
        except AdmissionRuntimeError as exc:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderPolicyError(
                "image variation usage reconciliation failed"
            ) from exc

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
    ) -> ProviderImageResponse:
        if not isinstance(image, bytes) or not image:
            raise ProviderInvocationError("image edit source must be non-empty bytes")
        if len(image) > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image edit source exceeded size limit")
        if mask is not None and len(mask) > _MAX_PROVIDER_MEDIA_BYTES:
            raise ProviderInvocationError("image edit mask exceeded size limit")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ProviderInvocationError("image edit prompt must be non-empty")

        governance, lease, estimate = _require_media_policy(
            provider_id=self.provider_id,
            purpose="image-edit",
            data_class=data_class,
            tenant_id=tenant_id,
            operation_id=operation_id,
            content=image + prompt.encode("utf-8"),
            estimated_cost_usd=0.0,
            resource_budget=ResourceBudget(),
            timeout_seconds=self.timeout_seconds,
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
        try:
            client = self._get_client()
            try:
                response = await client.images.edit(**kwargs)
            except Exception as exc:
                raise ProviderInvocationError("image edit request failed") from exc
            images = _extract_b64_images(response, fallback_prompt=prompt)
        except BaseException:
            _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=_image_artifact_bytes(images),
        )
        try:
            self.admission_runtime.complete(lease.operation_id, actual)
        except AdmissionRuntimeError as exc:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderPolicyError(
                "image edit usage reconciliation failed"
            ) from exc

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

    async def synthesize_speech(
        self, request: ProviderSpeechRequest
    ) -> ProviderSpeechResponse:
        if not isinstance(request.text, str) or not request.text.strip():
            raise ProviderInvocationError("speech provider text must be non-empty")
        if len(request.text) > 16_384:
            raise ProviderInvocationError("speech provider text exceeded size limit")
        if not 0.25 <= float(request.speed) <= 4.0:
            raise ProviderInvocationError("speech provider speed is unsupported")
        if request.response_format not in {"mp3", "wav", "opus", "aac", "flac", "pcm"}:
            raise ProviderInvocationError("speech provider format is unsupported")

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
            timeout_seconds=self.timeout_seconds,
            provider_attempts=self.max_retries + 1,
            admission_runtime=self.admission_runtime,
        )
        started = time.perf_counter()
        try:
            client = self._get_client()
            try:
                response = await client.audio.speech.create(
                    model=request.model,
                    voice=request.voice,
                    input=request.text,
                    speed=request.speed,
                    response_format=request.response_format,
                )
                raw = getattr(response, "content", None)
                if raw is None:
                    reader = getattr(response, "read", None)
                    if reader is None:
                        raise ProviderInvocationError("speech provider returned malformed response")
                    raw = reader()
                    if inspect.isawaitable(raw):
                        raw = await raw
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
            _release_provider_lease(self.admission_runtime, lease)
            raise

        latency_seconds = max(0.0, time.perf_counter() - started)
        actual = _media_actual_usage(
            estimate,
            wall_seconds=latency_seconds,
            artifact_bytes=len(audio),
        )
        try:
            self.admission_runtime.complete(lease.operation_id, actual)
        except AdmissionRuntimeError as exc:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderPolicyError(
                "speech provider usage reconciliation failed"
            ) from exc

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
        self.api_key = (
            api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        ).strip()
        self.model = (model or os.getenv("AI_MODEL") or "gpt-5.5").strip()
        self.base_url = (
            base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "")
        ).strip()
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
    def _extract_response_text(payload: Any) -> str:
        if not isinstance(payload, Mapping):
            raise ProviderInvocationError("model provider returned malformed JSON")

        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        output = payload.get("output")
        if not isinstance(output, list):
            raise ProviderInvocationError("model provider returned malformed response")

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
        if not joined:
            raise ProviderInvocationError("model provider returned an empty response")
        return joined

    @staticmethod
    def _decode_response(response: Any) -> Mapping[str, Any]:
        return _read_provider_json(response)

    def generate_sync(self, request: ProviderRequest) -> ProviderResponse:
        model = _validate_request(request, default_model=self.model)
        self._ensure_architecture()

        effective_data_class, effective_purpose, effective_tenant_id = (
            _effective_governance_fields(
                data_class=request.data_class,
                purpose=request.purpose,
                tenant_id=request.tenant_id,
                governance_context=request.governance_context,
            )
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
            raise ProviderPolicyError(
                "model provider transfer denied by governance policy"
            ) from exc

        requested_output = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else min(4_096, request.resource_budget.max_output_tokens)
        )
        lease, estimate = _admit_provider_request(
            self.admission_runtime,
            request,
            tenant_id=effective_tenant_id,
            requested_output_tokens=requested_output,
            timeout_seconds=self.timeout_seconds,
            provider_attempts=self.max_retries + 1,
        )

        if not self.api_key:
            _release_provider_lease(self.admission_runtime, lease)
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")

        messages: list[dict[str, str]] = [
            message.as_openai_input() for message in request.history
        ]
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            "model": model,
            "instructions": request.instructions,
            "input": messages,
        }
        if request.max_output_tokens is not None:
            body["max_output_tokens"] = request.max_output_tokens
        if request.tool_schemas:
            body["tools"] = [dict(schema) for schema in request.tool_schemas]

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
        try:
            for _attempt in range(self.max_retries + 1):
                attempts_used += 1
                try:
                    with urllib.request.urlopen(
                        outbound,
                        timeout=self.timeout_seconds,
                    ) as response:
                        payload = self._decode_response(response)
                    text = self._extract_response_text(payload)
                    request_id = payload.get("id")
                    latency_seconds = max(0.0, time.perf_counter() - started)
                    actual = _actual_provider_usage(
                        payload,
                        estimate=estimate,
                        wall_seconds=latency_seconds,
                        attempts_used=attempts_used,
                    )
                    try:
                        self.admission_runtime.complete(
                            lease.operation_id,
                            actual,
                        )
                    except AdmissionRuntimeError as exc:
                        _release_provider_lease(self.admission_runtime, lease)
                        raise ProviderPolicyError(
                            "model provider usage reconciliation failed"
                        ) from exc
                    return ProviderResponse(
                        text=text,
                        provider=self.provider_id,
                        model=model,
                        request_id=(
                            str(request_id)
                            if isinstance(request_id, (str, int))
                            else None
                        ),
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
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    ValueError,
                ) as exc:
                    last_error = exc
                    continue
        except BaseException:
            _release_provider_lease(self.admission_runtime, lease)
            raise

        _release_provider_lease(self.admission_runtime, lease)
        raise ProviderInvocationError("model provider request failed") from last_error


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


__all__ = [
    "AIMessage",
    "OpenAIProviderAdapter",
    "OpenAISyncProviderAdapter",
    "ProviderAdapter",
    "ProviderError",
    "ProviderImageRequest",
    "ProviderImageResponse",
    "ProviderInvocationError",
    "ProviderPolicyError",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderSpeechRequest",
    "ProviderSpeechResponse",
    "ProviderUnavailableError",
    "normalize_history",
    "provider_request_from_context",
]
