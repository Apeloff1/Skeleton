"""Backend client for the canonical Skeleton cognitive-execution engine.

This module is an application-boundary client only.  It does not own provider
credentials, provider transports, execution persistence, or tool authority.

The backend may construct a request-bound delegated capability and submit a
fully compiled immutable ContextEnvelope to the engine service.  Once an engine
URL is configured, transport failures are fail-closed: callers must not execute
a second local provider request as a fallback because doing so would violate
idempotency, budget and credential-ownership guarantees.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from time import monotonic
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import httpx

from skeleton.api.engine_authority import DelegatedAuthority, engine_request_binding
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.context import ContextEnvelope
from skeleton.contracts.operation import OperationEnvelope
from skeleton.provider_contract import ProviderToolDefinition


class EngineClientError(RuntimeError):
    """Base application-side engine boundary failure."""


class EngineUnavailableError(EngineClientError):
    """The engine boundary could not be reached safely."""


class EngineProtocolError(EngineClientError):
    """The engine returned a malformed or incompatible payload."""


class EngineConflictError(EngineClientError):
    """The engine rejected an idempotency or state conflict."""


class EngineNotFoundError(EngineProtocolError):
    """The requested engine resource does not exist."""


class EngineAuthorizationError(EngineClientError):
    """The engine rejected delegated authority."""


class EngineExecutionFailed(EngineClientError):
    """A submitted engine execution reached a non-success terminal state."""

    def __init__(
        self,
        message: str,
        *,
        execution_id: str,
        status: str,
        failure_code: str | None = None,
        result: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.execution_id = execution_id
        self.status = status
        self.failure_code = failure_code
        self.result = None if result is None else dict(result)


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EngineProtocolError(f"{field} must be non-empty text")
    normalized = value.strip()
    if normalized != value:
        raise EngineProtocolError(f"{field} must be normalized")
    if len(normalized) > maximum:
        raise EngineProtocolError(f"{field} exceeds maximum length")
    return normalized


def _positive_float(value: object, field: str, *, maximum: float) -> float:
    if isinstance(value, bool):
        raise EngineProtocolError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(f"{field} must be numeric") from exc
    if result <= 0 or result > maximum or result != result:
        raise EngineProtocolError(f"{field} is outside allowed range")
    return result


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineProtocolError(f"{field} must be an integer")
    if value < 1 or value > maximum:
        raise EngineProtocolError(f"{field} is outside allowed range")
    return value


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise EngineProtocolError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise EngineProtocolError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineProtocolError(f"{field} must be an object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class EngineClientConfig:
    """Bounded application-side engine transport configuration."""

    base_url: str
    service_token: str | None = field(default=None, repr=False)
    service_principal: str = "codedock-backend"
    request_timeout_s: float = 15.0
    poll_interval_s: float = 0.05
    execution_timeout_s: float = 120.0
    max_response_bytes: int = 4 * 1024 * 1024
    max_media_response_bytes: int = 48 * 1024 * 1024
    max_poll_attempts: int = 2400

    def __post_init__(self) -> None:
        base = _text(self.base_url.rstrip("/"), "base_url", maximum=4096)
        if not (base.startswith("http://") or base.startswith("https://")):
            raise EngineProtocolError("engine base_url must use http or https")
        object.__setattr__(self, "base_url", base)
        token = self.service_token
        if token is not None:
            if (
                not isinstance(token, str)
                or token != token.strip()
                or len(token) < 32
                or len(token) > 4096
            ):
                raise EngineProtocolError(
                    "engine service token must be normalized and at least 32 characters"
                )
            object.__setattr__(self, "service_token", token)
        object.__setattr__(
            self,
            "service_principal",
            _text(self.service_principal, "service_principal", maximum=512),
        )
        object.__setattr__(
            self,
            "request_timeout_s",
            _positive_float(
                self.request_timeout_s,
                "request_timeout_s",
                maximum=300.0,
            ),
        )
        object.__setattr__(
            self,
            "poll_interval_s",
            _positive_float(
                self.poll_interval_s,
                "poll_interval_s",
                maximum=10.0,
            ),
        )
        object.__setattr__(
            self,
            "execution_timeout_s",
            _positive_float(
                self.execution_timeout_s,
                "execution_timeout_s",
                maximum=86_400.0,
            ),
        )
        object.__setattr__(
            self,
            "max_response_bytes",
            _positive_int(
                self.max_response_bytes,
                "max_response_bytes",
                maximum=64 * 1024 * 1024,
            ),
        )
        object.__setattr__(
            self,
            "max_media_response_bytes",
            _positive_int(
                self.max_media_response_bytes,
                "max_media_response_bytes",
                maximum=128 * 1024 * 1024,
            ),
        )
        object.__setattr__(
            self,
            "max_poll_attempts",
            _positive_int(
                self.max_poll_attempts,
                "max_poll_attempts",
                maximum=1_000_000,
            ),
        )

    @classmethod
    def from_env(cls) -> "EngineClientConfig | None":
        raw_url = os.getenv("SKELETON_INTERNAL_URL")
        if raw_url is None or not raw_url.strip():
            return None
        raw_token = os.getenv("SKL_ENGINE_SERVICE_TOKEN")
        if raw_token is None or not raw_token.strip():
            raise EngineProtocolError(
                "engine service token is required when engine URL is configured"
            )
        try:
            return cls(
                base_url=raw_url.strip(),
                service_token=raw_token.strip(),
                service_principal=(
                    os.getenv(
                        "SKL_ENGINE_SERVICE_PRINCIPAL",
                        "codedock-backend",
                    ).strip()
                    or "codedock-backend"
                ),
                request_timeout_s=float(
                    os.getenv("SKELETON_ENGINE_REQUEST_TIMEOUT_S", "15")
                ),
                poll_interval_s=float(
                    os.getenv("SKELETON_ENGINE_POLL_INTERVAL_S", "0.05")
                ),
                execution_timeout_s=float(
                    os.getenv("SKELETON_ENGINE_EXECUTION_TIMEOUT_S", "120")
                ),
                max_response_bytes=int(
                    os.getenv(
                        "SKELETON_ENGINE_MAX_RESPONSE_BYTES",
                        str(4 * 1024 * 1024),
                    )
                ),
                max_media_response_bytes=int(
                    os.getenv(
                        "SKELETON_ENGINE_MAX_MEDIA_RESPONSE_BYTES",
                        str(48 * 1024 * 1024),
                    )
                ),
                max_poll_attempts=int(
                    os.getenv("SKELETON_ENGINE_MAX_POLL_ATTEMPTS", "2400")
                ),
            )
        except (TypeError, ValueError) as exc:
            raise EngineProtocolError(
                "engine environment configuration is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class EngineTerminalResult:
    """Normalized terminal result returned to application routes."""

    operation_id: str
    execution_id: str
    status: str
    final_output: str
    usage: Mapping[str, Any]
    verification: str | None
    verification_receipt: Mapping[str, Any] | None
    evidence_refs: tuple[str, ...]
    provider_receipts: tuple[str, ...]
    tool_receipts: tuple[str, ...]
    memory_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    stream_terminal_event: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EngineTerminalResult":
        body = _json_object(payload, "result")
        status = _text(body.get("status"), "result.status", maximum=64)
        if status != "completed":
            usage = _json_object(body.get("usage", {}), "result.usage")
            failure_code = (
                None
                if usage.get("error_code") is None
                else str(usage["error_code"])
            )
            raise EngineExecutionFailed(
                "engine execution did not complete successfully"
                + (" (" + failure_code + ")" if failure_code else ""),
                execution_id=str(body.get("execution_id") or ""),
                status=status,
                failure_code=failure_code,
                result=body,
            )
        final_output = body.get("final_output")
        if not isinstance(final_output, str) or not final_output.strip():
            raise EngineProtocolError(
                "completed engine result is missing final_output"
            )
        verification_receipt = body.get("verification_receipt")
        if verification_receipt is not None and not isinstance(
            verification_receipt,
            Mapping,
        ):
            raise EngineProtocolError(
                "engine verification_receipt must be an object"
            )

        def refs(field: str) -> tuple[str, ...]:
            raw = body.get(field, [])
            if not isinstance(raw, list) or any(
                not isinstance(item, str) or not item.strip() for item in raw
            ):
                raise EngineProtocolError(
                    f"engine result {field} must be a string list"
                )
            return tuple(dict.fromkeys(item.strip() for item in raw))

        return cls(
            operation_id=_text(
                body.get("operation_id"),
                "result.operation_id",
                maximum=192,
            ),
            execution_id=_text(
                body.get("execution_id"),
                "result.execution_id",
                maximum=192,
            ),
            status=status,
            final_output=final_output.strip(),
            usage=_json_object(body.get("usage", {}), "result.usage"),
            verification=(
                None
                if body.get("verification") is None
                else _text(
                    body.get("verification"),
                    "result.verification",
                    maximum=4096,
                )
            ),
            verification_receipt=(
                None
                if verification_receipt is None
                else dict(verification_receipt)
            ),
            evidence_refs=refs("evidence_refs"),
            provider_receipts=refs("provider_receipts"),
            tool_receipts=refs("tool_receipts"),
            memory_refs=refs("memory_refs"),
            artifact_refs=refs("artifact_refs"),
            stream_terminal_event=(
                None
                if body.get("stream_terminal_event") is None
                else _text(
                    body.get("stream_terminal_event"),
                    "result.stream_terminal_event",
                    maximum=4096,
                )
            ),
        )


def command_from_context(
    *,
    context: ContextEnvelope,
    actor_id: str,
    capability: str,
    idempotency_key: str,
    instructions: str,
    prompt: str,
    objective: str | None = None,
    verification_profile: str = "evidence_required",
    history: Sequence[Mapping[str, str]] = (),
    service_principal: str = "codedock-backend",
    created_at: datetime | None = None,
    deadline: datetime | None = None,
    trace_id: str | None = None,
    max_model_turns: int = 4,
    max_output_tokens: int | None = None,
    max_tool_calls: int = 1,
    max_repeat_tool_batches: int = 1,
    tools: Sequence[ProviderToolDefinition] = (),
    tool_choice: str | None = None,
    specific_tool_id: str | None = None,
    context_seed_refs: Sequence[str] = (),
) -> EngineExecutionCommand:
    """Build a digest-bound engine command from one immutable context snapshot."""

    if not isinstance(context, ContextEnvelope):
        raise TypeError("context must be ContextEnvelope")
    actor = _text(actor_id, "actor_id", maximum=512)
    cap = _text(capability, "capability", maximum=256)
    idem = _text(idempotency_key, "idempotency_key", maximum=1024)
    principal = _text(
        service_principal,
        "service_principal",
        maximum=512,
    )
    instruction_text = _text(
        str(instructions).strip(),
        "instructions",
        maximum=1_000_000,
    )
    prompt_text = _text(
        str(prompt).strip(),
        "prompt",
        maximum=1_000_000,
    )
    objective_text = _text(
        (
            str(objective).strip()
            if objective is not None
            else (
                prompt_text
                if len(prompt_text) <= 65_536
                else "Execute canonical context turn " + context.turn_id
            )
        ),
        "objective",
        maximum=65_536,
    )
    profile = _text(
        str(verification_profile).strip(),
        "verification_profile",
        maximum=64,
    )
    if profile not in {"evidence_required", "assistant_proposal"}:
        raise EngineProtocolError("verification_profile is unsupported")
    if profile == "assistant_proposal" and cap not in {
        "assistant.chat",
        "assistant.compat",
    }:
        raise EngineProtocolError(
            "assistant_proposal verification requires assistant capability"
        )
    started = _aware(
        created_at or datetime.now(timezone.utc),
        "created_at",
    )
    due = _aware(
        deadline or (started + timedelta(seconds=120)),
        "deadline",
    )
    if due <= started:
        raise EngineProtocolError("deadline must be later than created_at")
    if due - started > timedelta(days=1):
        raise EngineProtocolError("engine execution deadline exceeds hard limit")

    normalized_tools: list[ProviderToolDefinition] = []
    seen_tool_ids: set[str] = set()
    for index, tool in enumerate(tools):
        if not isinstance(tool, ProviderToolDefinition):
            raise EngineProtocolError(
                f"tools[{index}] must be ProviderToolDefinition"
            )
        if tool.tool_id in seen_tool_ids:
            raise EngineProtocolError(
                "tools contain duplicate tool_id"
            )
        seen_tool_ids.add(tool.tool_id)
        normalized_tools.append(tool)
        if len(normalized_tools) > 256:
            raise EngineProtocolError("tools exceed maximum count")

    resolved_tool_choice = (
        ("auto" if normalized_tools else "none")
        if tool_choice is None
        else _text(
            str(tool_choice).strip().lower(),
            "tool_choice",
            maximum=32,
        )
    )
    if resolved_tool_choice not in {
        "none",
        "auto",
        "required",
        "specific",
    }:
        raise EngineProtocolError("tool_choice is unsupported")
    if not normalized_tools and resolved_tool_choice != "none":
        raise EngineProtocolError(
            "tool_choice requires at least one offered tool"
        )
    if normalized_tools and resolved_tool_choice == "none":
        raise EngineProtocolError(
            "offered tools require an executable tool_choice"
        )
    normalized_specific_tool_id = (
        None
        if specific_tool_id is None
        else _text(
            str(specific_tool_id).strip(),
            "specific_tool_id",
            maximum=512,
        )
    )
    if resolved_tool_choice == "specific":
        if normalized_specific_tool_id is None:
            raise EngineProtocolError(
                "specific tool choice requires specific_tool_id"
            )
        if normalized_specific_tool_id not in seen_tool_ids:
            raise EngineProtocolError(
                "specific_tool_id is not offered"
            )
    elif normalized_specific_tool_id is not None:
        raise EngineProtocolError(
            "specific_tool_id requires tool_choice='specific'"
        )
    if profile == "assistant_proposal" and normalized_tools:
        raise EngineProtocolError(
            "assistant_proposal verification requires tool-free execution"
        )

    normalized_history: list[tuple[str, str]] = []
    for index, item in enumerate(history):
        if not isinstance(item, Mapping):
            raise EngineProtocolError(
                f"history[{index}] must be an object"
            )
        role = _text(item.get("role"), f"history[{index}].role", maximum=32)
        if role not in {"user", "assistant"}:
            raise EngineProtocolError(
                f"history[{index}].role is not supported"
            )
        content = _text(
            str(item.get("content") or "").strip(),
            f"history[{index}].content",
            maximum=1_000_000,
        )
        normalized_history.append((role, content))
        if len(normalized_history) > 1024:
            raise EngineProtocolError("history exceeds maximum turn count")

    resource_budget = {
        "max_model_turns": _positive_int(
            max_model_turns,
            "max_model_turns",
            maximum=64,
        ),
        "max_tool_calls": _positive_int(
            max_tool_calls,
            "max_tool_calls",
            maximum=1024,
        ),
        "max_elapsed_seconds": (due - started).total_seconds(),
    }
    if max_output_tokens is not None:
        resource_budget["max_output_tokens"] = _positive_int(
            max_output_tokens,
            "max_output_tokens",
            maximum=131_072,
        )
    stop_policy = {
        "max_repeat_tool_batches": _positive_int(
            max_repeat_tool_batches,
            "max_repeat_tool_batches",
            maximum=64,
        ),
    }

    operation = OperationEnvelope(
        operation_id=context.operation_id,
        tenant_id=context.tenant_id,
        actor_id=actor,
        capability=cap,
        created_at=started,
        deadline=due,
        idempotency_key=idem,
        trace_id=_text(
            trace_id or ("engine:" + context.operation_id),
            "trace_id",
            maximum=512,
        ),
    )
    handoff = EngineContextHandoff(
        operation_id=context.operation_id,
        execution_id=context.execution_id,
        turn_id=context.turn_id,
        tenant_id=context.tenant_id,
        context_id=context.context_id,
        context_digest=context.context_digest,
        compiler_version=context.compiler_version,
        source_snapshot=context.source_snapshot,
        data_class=max(
            (
                segment.data_class
                for segment in context.selected_segments
            ),
            default="internal",
            key=("public", "internal", "confidential", "restricted").index,
        ),
        instructions=instruction_text,
        prompt=prompt_text,
        history=tuple(normalized_history),
        tools=tuple(normalized_tools),
        tool_choice=resolved_tool_choice,
        specific_tool_id=normalized_specific_tool_id,
    )
    execution_request = AIExecutionRequest(
        operation_id=context.operation_id,
        execution_id=context.execution_id,
        objective=objective_text,
        context_policy={
            "tenant_id": context.tenant_id,
            "capability": cap,
            "verification_profile": profile,
            "data_class": handoff.data_class,
            "context_id": context.context_id,
            "context_digest": context.context_digest,
            "compiler_version": context.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "tool_choice": resolved_tool_choice,
            "specific_tool_id": normalized_specific_tool_id,
            "source_snapshot": [
                [segment_id, digest]
                for segment_id, digest in context.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": context.tenant_id,
            "allowed_tool_ids": [
                tool.tool_id
                for tool in normalized_tools
            ],
        },
        resource_budget=resource_budget,
        stop_policy=stop_policy,
        created_at=started,
    )
    authority_expiry = min(
        due,
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    if authority_expiry <= started:
        authority_expiry = min(due, started + timedelta(seconds=1))
    authority_scopes = [
        "engine:submit",
        "engine:read",
        "engine:cancel",
        "engine:events",
    ]
    if normalized_tools:
        authority_scopes.append("engine:approve")

    authority = DelegatedAuthority(
        service_principal=principal,
        actor_id=actor,
        tenant_id=context.tenant_id,
        scopes=tuple(authority_scopes),
        capability=cap,
        issued_at=started,
        expires_at=authority_expiry,
        request_binding=engine_request_binding(
            operation,
            execution_request,
        ),
    )

    refs: list[str] = []
    for raw in context_seed_refs:
        ref = _text(raw, "context_seed_ref", maximum=2048)
        if ref not in refs:
            refs.append(ref)
        if len(refs) > 1024:
            raise EngineProtocolError(
                "too many context seed references"
            )

    return EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=tuple(refs),
        resource_budget=resource_budget,
        stream_preferences={
            "mode": "events",
            "provisional": True,
            "terminal_reconciliation": True,
        },
    )


class EngineClient:
    """Bounded async HTTP client for the canonical engine API."""

    _TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})

    def __init__(
        self,
        config: EngineClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(config, EngineClientConfig):
            raise TypeError("config must be EngineClientConfig")
        self.config = config
        self._transport = transport

    @classmethod
    def from_env(
        cls,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "EngineClient | None":
        config = EngineClientConfig.from_env()
        if config is None:
            return None
        return cls(config, transport=transport)

    def _url(self, suffix: str) -> str:
        if not suffix.startswith("/"):
            raise EngineProtocolError("engine path must be absolute")
        return (
            self.config.base_url
            + "/api/v1/engine"
            + suffix
        )

    def _headers(self, *, trace_id: str | None = None) -> dict[str, str]:
        token = self.config.service_token
        if token is None:
            raise EngineAuthorizationError(
                "engine service token is not configured"
            )
        headers = {
            "authorization": "Bearer " + token,
            "x-zaibatsu-attester": self.config.service_principal,
            "accept": "application/json",
        }
        if trace_id:
            headers["x-trace-id"] = _text(
                trace_id,
                "trace_id",
                maximum=512,
            )
        return headers

    async def _request(
        self,
        method: str,
        suffix: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        trace_id: str | None = None,
        max_response_bytes: int | None = None,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self.config.request_timeout_s)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    self._url(suffix),
                    headers=self._headers(trace_id=trace_id),
                    json=None if json_body is None else dict(json_body),
                    params=None if params is None else dict(params),
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise EngineUnavailableError(
                "engine transport is unavailable"
            ) from exc
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(
                "engine transport failed"
            ) from exc

        response_limit = (
            self.config.max_response_bytes
            if max_response_bytes is None
            else _positive_int(
                max_response_bytes,
                "max_response_bytes",
                maximum=128 * 1024 * 1024,
            )
        )
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                advertised = int(content_length)
            except ValueError as exc:
                raise EngineProtocolError(
                    "engine content-length is invalid"
                ) from exc
            if advertised > response_limit:
                raise EngineProtocolError(
                    "engine response exceeds configured size bound"
                )
        if len(response.content) > response_limit:
            raise EngineProtocolError(
                "engine response exceeds configured size bound"
            )

        if response.status_code == 404:
            raise EngineNotFoundError("engine resource was not found")
        if response.status_code == 409:
            raise EngineConflictError("engine rejected conflicting request")
        if response.status_code in {401, 403}:
            raise EngineAuthorizationError(
                "engine rejected delegated authority"
            )
        if response.status_code >= 500:
            raise EngineUnavailableError(
                "engine service is unavailable"
            )
        if response.status_code >= 400:
            raise EngineProtocolError(
                f"engine rejected request with status {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EngineProtocolError(
                "engine returned invalid JSON"
            ) from exc
        if not isinstance(payload, Mapping):
            raise EngineProtocolError(
                "engine response must be an object"
            )
        return dict(payload)

    @staticmethod
    def _validate_image_payload(
        payload: Mapping[str, Any],
        *,
        maximum_items: int = 4,
    ) -> dict[str, Any]:
        images = payload.get("images")
        if (
            not isinstance(images, list)
            or not images
            or len(images) > maximum_items
        ):
            raise EngineProtocolError(
                "engine image response has invalid image count"
            )
        for item in images:
            if not isinstance(item, Mapping):
                raise EngineProtocolError(
                    "engine image item must be an object"
                )
            data = item.get("data")
            if not isinstance(data, str) or not data:
                raise EngineProtocolError(
                    "engine image item is missing base64 data"
                )
            if len(data) > 32 * 1024 * 1024:
                raise EngineProtocolError(
                    "engine image payload exceeds size bound"
                )
            try:
                decoded = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise EngineProtocolError(
                    "engine image payload is invalid base64"
                ) from exc
            if not decoded or len(decoded) > 24 * 1024 * 1024:
                raise EngineProtocolError(
                    "engine image payload exceeds decoded size bound"
                )
        return dict(payload)

    async def generate_image(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        operation_id: str,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        count: int = 1,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/media/images/generate",
            json_body={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(tenant_id, "tenant_id", maximum=512),
                "operation_id": _text(
                    operation_id,
                    "operation_id",
                    maximum=512,
                ),
                "prompt": _text(prompt, "prompt", maximum=16_384),
                "size": _text(size, "size", maximum=64),
                "quality": _text(quality, "quality", maximum=64),
                "count": _positive_int(count, "count", maximum=4),
            },
            trace_id=trace_id,
            max_response_bytes=self.config.max_media_response_bytes,
        )
        return self._validate_image_payload(payload, maximum_items=count)

    async def create_image_variation(
        self,
        image: bytes,
        *,
        actor_id: str,
        tenant_id: str,
        operation_id: str,
        count: int = 1,
        size: str = "1024x1024",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(image, (bytes, bytearray)) or not image:
            raise EngineProtocolError("image must be non-empty bytes")
        if len(image) > 20 * 1024 * 1024:
            raise EngineProtocolError("image exceeds media size bound")
        payload = await self._request(
            "POST",
            "/media/images/variation",
            json_body={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(tenant_id, "tenant_id", maximum=512),
                "operation_id": _text(
                    operation_id,
                    "operation_id",
                    maximum=512,
                ),
                "image_base64": base64.b64encode(bytes(image)).decode("ascii"),
                "count": _positive_int(count, "count", maximum=4),
                "size": _text(size, "size", maximum=64),
            },
            trace_id=trace_id,
            max_response_bytes=self.config.max_media_response_bytes,
        )
        return self._validate_image_payload(payload, maximum_items=count)

    async def edit_image(
        self,
        image: bytes,
        *,
        prompt: str,
        actor_id: str,
        tenant_id: str,
        operation_id: str,
        mask: bytes | None = None,
        size: str = "1024x1024",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(image, (bytes, bytearray)) or not image:
            raise EngineProtocolError("image must be non-empty bytes")
        if len(image) > 20 * 1024 * 1024:
            raise EngineProtocolError("image exceeds media size bound")
        if mask is not None and (
            not isinstance(mask, (bytes, bytearray))
            or not mask
            or len(mask) > 20 * 1024 * 1024
        ):
            raise EngineProtocolError("mask exceeds media size bound")
        payload = await self._request(
            "POST",
            "/media/images/edit",
            json_body={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(tenant_id, "tenant_id", maximum=512),
                "operation_id": _text(
                    operation_id,
                    "operation_id",
                    maximum=512,
                ),
                "image_base64": base64.b64encode(bytes(image)).decode("ascii"),
                "mask_base64": (
                    None
                    if mask is None
                    else base64.b64encode(bytes(mask)).decode("ascii")
                ),
                "prompt": _text(prompt, "prompt", maximum=16_384),
                "size": _text(size, "size", maximum=64),
            },
            trace_id=trace_id,
            max_response_bytes=self.config.max_media_response_bytes,
        )
        return self._validate_image_payload(payload, maximum_items=1)

    async def synthesize_speech(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        operation_id: str,
        text: str,
        voice: str = "nova",
        speed: float = 1.0,
        response_format: str = "mp3",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/media/speech",
            json_body={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(tenant_id, "tenant_id", maximum=512),
                "operation_id": _text(
                    operation_id,
                    "operation_id",
                    maximum=512,
                ),
                "text": _text(text, "text", maximum=16_384),
                "voice": _text(voice, "voice", maximum=128),
                "speed": _positive_float(speed, "speed", maximum=4.0),
                "response_format": _text(
                    response_format,
                    "response_format",
                    maximum=16,
                ),
            },
            trace_id=trace_id,
            max_response_bytes=self.config.max_media_response_bytes,
        )
        raw = payload.get("audio_base64")
        if not isinstance(raw, str) or not raw:
            raise EngineProtocolError(
                "engine speech response is missing audio"
            )
        try:
            audio = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise EngineProtocolError(
                "engine speech payload is invalid base64"
            ) from exc
        if not audio or len(audio) > 24 * 1024 * 1024:
            raise EngineProtocolError(
                "engine speech payload exceeds size bound"
            )
        payload = dict(payload)
        payload["audio"] = audio
        return payload

    async def submit(
        self,
        command: EngineExecutionCommand,
    ) -> dict[str, Any]:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError("command must be EngineExecutionCommand")
        return await self._request(
            "POST",
            "/executions",
            json_body={
                "actor_id": command.operation.actor_id,
                "tenant_id": command.operation.tenant_id,
                "command": command.as_dict(),
            },
            trace_id=command.operation.trace_id,
        )

    async def status(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        execution = quote(
            _text(execution_id, "execution_id", maximum=192),
            safe="",
        )
        return await self._request(
            "GET",
            f"/executions/{execution}",
            params={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(
                    tenant_id,
                    "tenant_id",
                    maximum=512,
                ),
            },
            trace_id=trace_id,
        )

    async def events(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        execution = quote(
            _text(execution_id, "execution_id", maximum=192),
            safe="",
        )
        return await self._request(
            "GET",
            f"/executions/{execution}/events",
            params={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(
                    tenant_id,
                    "tenant_id",
                    maximum=512,
                ),
            },
            trace_id=trace_id,
        )

    async def cancel(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        reason: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        execution = quote(
            _text(execution_id, "execution_id", maximum=192),
            safe="",
        )
        return await self._request(
            "POST",
            f"/executions/{execution}/cancel",
            json_body={
                "actor_id": _text(
                    actor_id,
                    "actor_id",
                    maximum=512,
                ),
                "tenant_id": _text(
                    tenant_id,
                    "tenant_id",
                    maximum=512,
                ),
                "reason": _text(
                    reason,
                    "reason",
                    maximum=2048,
                ),
            },
            trace_id=trace_id,
        )

    async def pending_tool_approvals(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        trace_id: str | None = None,
    ) -> tuple[dict[str, str], ...]:
        execution = quote(
            _text(execution_id, "execution_id", maximum=192),
            safe="",
        )
        payload = await self._request(
            "GET",
            f"/executions/{execution}/tool-approvals/pending",
            params={
                "actor_id": _text(actor_id, "actor_id", maximum=512),
                "tenant_id": _text(
                    tenant_id,
                    "tenant_id",
                    maximum=512,
                ),
            },
            trace_id=trace_id,
        )
        if payload.get("execution_id") != execution_id:
            raise EngineProtocolError(
                "pending approval execution identity mismatch"
            )
        raw_pending = payload.get("pending")
        if not isinstance(raw_pending, list):
            raise EngineProtocolError(
                "pending approval response is malformed"
            )
        rows: list[dict[str, str]] = []
        seen_calls: set[str] = set()
        for index, raw in enumerate(raw_pending):
            if not isinstance(raw, Mapping):
                raise EngineProtocolError(
                    f"pending[{index}] must be an object"
                )
            call_id = _text(
                raw.get("call_id"),
                f"pending[{index}].call_id",
                maximum=256,
            )
            if call_id in seen_calls:
                raise EngineProtocolError(
                    "pending approval response has duplicate call_id"
                )
            seen_calls.add(call_id)
            tool_id = _text(
                raw.get("tool_id"),
                f"pending[{index}].tool_id",
                maximum=128,
            )
            digest = _text(
                raw.get("arguments_digest"),
                f"pending[{index}].arguments_digest",
                maximum=64,
            )
            if (
                len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise EngineProtocolError(
                    "pending approval arguments_digest is invalid"
                )
            idem = _text(
                raw.get("idempotency_key"),
                f"pending[{index}].idempotency_key",
                maximum=1024,
            )
            approval_ref = _text(
                raw.get("approval_ref"),
                f"pending[{index}].approval_ref",
                maximum=1024,
            )
            if not approval_ref.startswith("approval:"):
                raise EngineProtocolError(
                    "pending approval_ref is invalid"
                )
            rows.append(
                {
                    "call_id": call_id,
                    "tool_id": tool_id,
                    "arguments_digest": digest,
                    "idempotency_key": idem,
                    "approval_ref": approval_ref,
                }
            )
        return tuple(rows)

    async def approve_tool_call(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        call_id: str,
        tool_id: str,
        arguments_digest: str,
        idempotency_key: str,
        expires_at: datetime,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        execution = quote(
            _text(execution_id, "execution_id", maximum=192),
            safe="",
        )
        expiry = _aware(expires_at, "expires_at")
        digest = _text(
            arguments_digest,
            "arguments_digest",
            maximum=64,
        )
        if (
            len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise EngineProtocolError(
                "arguments_digest must be lowercase sha256"
            )
        payload = await self._request(
            "POST",
            f"/executions/{execution}/tool-approvals",
            json_body={
                "actor_id": _text(
                    actor_id,
                    "actor_id",
                    maximum=512,
                ),
                "tenant_id": _text(
                    tenant_id,
                    "tenant_id",
                    maximum=512,
                ),
                "call_id": _text(
                    call_id,
                    "call_id",
                    maximum=256,
                ),
                "tool_id": _text(
                    tool_id,
                    "tool_id",
                    maximum=128,
                ),
                "arguments_digest": digest,
                "idempotency_key": _text(
                    idempotency_key,
                    "idempotency_key",
                    maximum=1024,
                ),
                "expires_at": expiry.isoformat(),
            },
            trace_id=trace_id,
        )
        if payload.get("execution_id") != execution_id:
            raise EngineProtocolError(
                "approval execution identity mismatch"
            )
        approval_id = _text(
            payload.get("approval_id"),
            "approval_id",
            maximum=2048,
        )
        approval_ref = _text(
            payload.get("approval_ref"),
            "approval_ref",
            maximum=1024,
        )
        if not approval_ref.startswith("approval:"):
            raise EngineProtocolError(
                "approval response has invalid approval_ref"
            )
        if payload.get("call_id") != call_id:
            raise EngineProtocolError(
                "approval call identity mismatch"
            )
        if payload.get("tool_id") != tool_id:
            raise EngineProtocolError(
                "approval tool identity mismatch"
            )
        if payload.get("arguments_digest") != digest:
            raise EngineProtocolError(
                "approval arguments identity mismatch"
            )
        result = dict(payload)
        result["approval_id"] = approval_id
        result["approval_ref"] = approval_ref
        return result

    @staticmethod
    def _result_from_events(
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        events = payload.get("events")
        if not isinstance(events, list):
            raise EngineProtocolError(
                "engine events response is missing events"
            )
        result: Mapping[str, Any] | None = None
        seen_ids: set[str] = set()
        last_sequence = -1
        for event in events:
            if not isinstance(event, Mapping):
                raise EngineProtocolError(
                    "engine event must be an object"
                )
            event_id = _text(
                event.get("event_id"),
                "event.event_id",
                maximum=4096,
            )
            if event_id in seen_ids:
                raise EngineProtocolError(
                    "engine event stream contains duplicate event id"
                )
            seen_ids.add(event_id)
            sequence = event.get("sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence < 0
            ):
                raise EngineProtocolError(
                    "engine event sequence is invalid"
                )
            if sequence <= last_sequence:
                raise EngineProtocolError(
                    "engine event stream is not strictly ordered"
                )
            last_sequence = sequence
            if event.get("type") == "execution.result":
                candidate = event.get("result")
                if not isinstance(candidate, Mapping):
                    raise EngineProtocolError(
                        "execution.result event is malformed"
                    )
                result = candidate
        return result

    async def wait_for_terminal(
        self,
        *,
        execution_id: str,
        actor_id: str,
        tenant_id: str,
        trace_id: str | None = None,
        timeout_s: float | None = None,
    ) -> EngineTerminalResult:
        timeout = (
            self.config.execution_timeout_s
            if timeout_s is None
            else _positive_float(
                timeout_s,
                "timeout_s",
                maximum=86_400.0,
            )
        )
        started = monotonic()
        attempts = 0
        while True:
            attempts += 1
            if attempts > self.config.max_poll_attempts:
                raise EngineUnavailableError(
                    "engine polling budget exhausted"
                )
            if monotonic() - started > timeout:
                raise EngineUnavailableError(
                    "engine execution did not reach terminal state in time"
                )

            status = await self.status(
                execution_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                trace_id=trace_id,
            )
            state = _text(
                status.get("execution_state"),
                "execution_state",
                maximum=64,
            )
            if state in self._TERMINAL_STATES:
                events = await self.events(
                    execution_id,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                )
                result = self._result_from_events(events)
                if result is None:
                    raise EngineProtocolError(
                        "terminal engine execution is missing result event"
                    )
                if state != "completed":
                    usage = result.get("usage")
                    failure_code = (
                        str(usage.get("error_code"))
                        if isinstance(usage, Mapping)
                        and usage.get("error_code") is not None
                        else (
                            None
                            if status.get("failure_code") is None
                            else str(status["failure_code"])
                        )
                    )
                    raise EngineExecutionFailed(
                        "engine execution reached non-success terminal state"
                        + (" (" + failure_code + ")" if failure_code else ""),
                        execution_id=execution_id,
                        status=state,
                        failure_code=failure_code,
                        result=result,
                    )
                normalized = EngineTerminalResult.from_payload(result)
                if normalized.execution_id != execution_id:
                    raise EngineProtocolError(
                        "terminal result execution identity mismatch"
                    )
                return normalized

            await asyncio.sleep(self.config.poll_interval_s)

    async def _recover_ambiguous_submit(
        self,
        command: EngineExecutionCommand,
    ) -> bool:
        """Return True only when status proves the deterministic execution exists."""

        try:
            status = await self.status(
                command.execution_request.execution_id,
                actor_id=command.operation.actor_id,
                tenant_id=command.operation.tenant_id,
                trace_id=command.operation.trace_id,
            )
        except EngineNotFoundError:
            return False

        operation_id = _text(
            status.get("operation_id"),
            "status.operation_id",
            maximum=192,
        )
        execution_id = _text(
            status.get("execution_id"),
            "status.execution_id",
            maximum=192,
        )
        if operation_id != command.operation.operation_id:
            raise EngineProtocolError(
                "recovered engine status operation identity mismatch"
            )
        if execution_id != command.execution_request.execution_id:
            raise EngineProtocolError(
                "recovered engine status execution identity mismatch"
            )
        return True

    @staticmethod
    def _validate_ack_identity(
        ack: Mapping[str, Any],
        command: EngineExecutionCommand,
    ) -> str:
        execution_id = _text(
            ack.get("execution_id"),
            "ack.execution_id",
            maximum=192,
        )
        if execution_id != command.execution_request.execution_id:
            raise EngineProtocolError(
                "engine acknowledgement execution identity mismatch"
            )
        ack_operation = _text(
            ack.get("operation_id"),
            "ack.operation_id",
            maximum=192,
        )
        if ack_operation != command.operation.operation_id:
            raise EngineProtocolError(
                "engine acknowledgement operation identity mismatch"
            )
        return execution_id

    async def execute(
        self,
        command: EngineExecutionCommand,
    ) -> EngineTerminalResult:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError("command must be EngineExecutionCommand")

        execution_id = command.execution_request.execution_id
        try:
            ack = await self.submit(command)
        except EngineUnavailableError as first_error:
            try:
                recovered = await self._recover_ambiguous_submit(command)
            except EngineUnavailableError:
                raise first_error
            if not recovered:
                try:
                    ack = await self.submit(command)
                except EngineUnavailableError as retry_error:
                    try:
                        recovered = await self._recover_ambiguous_submit(command)
                    except (EngineNotFoundError, EngineUnavailableError):
                        raise retry_error
                    if not recovered:
                        raise retry_error
                else:
                    execution_id = self._validate_ack_identity(ack, command)
            else:
                execution_id = command.execution_request.execution_id
        else:
            execution_id = self._validate_ack_identity(ack, command)

        return await self.wait_for_terminal(
            execution_id=execution_id,
            actor_id=command.operation.actor_id,
            tenant_id=command.operation.tenant_id,
            trace_id=command.operation.trace_id,
        )


__all__ = [
    "EngineAuthorizationError",
    "EngineClient",
    "EngineClientConfig",
    "EngineClientError",
    "EngineConflictError",
    "EngineExecutionFailed",
    "EngineNotFoundError",
    "EngineProtocolError",
    "EngineTerminalResult",
    "EngineUnavailableError",
    "command_from_context",
]
