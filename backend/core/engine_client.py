"""Backend client for the canonical Skeleton cognitive-execution engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import socket
import time
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from skeleton.api.engine_authority import (
    DelegatedAuthority,
    engine_request_binding,
)
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
)
from skeleton.api.hmac_seal import mint_seal
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.context import ContextEnvelope
from skeleton.contracts.operation import OperationEnvelope
from skeleton.provider_runtime import (
    ProviderRequest,
    provider_request_from_context,
    provider_tool_definitions,
)


class EngineClientError(RuntimeError):
    """Base backend-to-engine failure."""


class EngineUnavailable(EngineClientError):
    """Engine endpoint or service credentials are unavailable."""


class EngineRequestConflict(EngineClientError):
    """Engine rejected a retry because canonical identity changed."""


class EngineExecutionFailed(EngineClientError):
    """Engine reached a terminal non-success result."""

    def __init__(self, message: str, *, status: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.status = dict(status or {})


class EngineApprovalRequired(EngineClientError):
    """Engine execution is suspended waiting for a bound tool approval."""

    def __init__(
        self,
        message: str,
        *,
        execution_id: str,
        status: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.execution_id = str(execution_id)
        self.status = dict(status or {})


class EngineDeadlineExceeded(EngineClientError):
    """Engine request exceeded the caller's monotonic deadline."""


@dataclass(frozen=True, slots=True)
class EngineClientConfig:
    base_url: str
    service_principal: str
    seal_secret: str
    timeout_seconds: float = 10.0
    retry_attempts: int = 3
    poll_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        base = str(self.base_url).strip().rstrip("/")
        principal = str(self.service_principal).strip()
        secret = str(self.seal_secret)
        if not base.startswith(("http://", "https://")):
            raise ValueError("engine base_url must be http(s)")
        if not principal:
            raise ValueError("engine service_principal is required")
        if not secret:
            raise ValueError("engine seal_secret is required")
        timeout = float(self.timeout_seconds)
        if timeout <= 0 or timeout > 120:
            raise ValueError("engine timeout_seconds is invalid")
        if (
            isinstance(self.retry_attempts, bool)
            or not isinstance(self.retry_attempts, int)
            or not 1 <= self.retry_attempts <= 10
        ):
            raise ValueError("engine retry_attempts is invalid")
        poll = float(self.poll_interval_seconds)
        if poll <= 0 or poll > 5:
            raise ValueError("engine poll_interval_seconds is invalid")
        object.__setattr__(self, "base_url", base)
        object.__setattr__(self, "service_principal", principal)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "poll_interval_seconds", poll)

    @classmethod
    def from_env(
        cls,
        source: Mapping[str, str] | None = None,
    ) -> "EngineClientConfig":
        env = os.environ if source is None else source
        base_url = (
            env.get("CODEDOCK_ENGINE_URL")
            or env.get("SKELETON_ENGINE_URL")
            or env.get("SKELETON_INTERNAL_URL")
            or "http://skeleton:8001"
        )
        principal = (
            env.get("CODEDOCK_ENGINE_SERVICE_PRINCIPAL")
            or "codedock-backend"
        )
        secret = env.get("GF_SEAL_SECRET") or ""
        return cls(
            base_url=base_url,
            service_principal=principal,
            seal_secret=secret,
            timeout_seconds=float(
                env.get("CODEDOCK_ENGINE_TIMEOUT_SECONDS", "10")
            ),
            retry_attempts=int(
                env.get("CODEDOCK_ENGINE_RETRY_ATTEMPTS", "3")
            ),
            poll_interval_seconds=float(
                env.get("CODEDOCK_ENGINE_POLL_INTERVAL_SECONDS", "0.1")
            ),
        )


def _deadline_remaining(deadline: datetime | None) -> float | None:
    if deadline is None:
        return None
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise EngineClientError("engine deadline must be timezone-aware")
    remaining = (
        deadline.astimezone(timezone.utc)
        - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining <= 0:
        raise EngineDeadlineExceeded("engine deadline exceeded")
    return remaining


def _strict_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineClientError(f"{field} must be an object")
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
        raise EngineClientError(f"{field} must be deterministic JSON") from exc
    return result


class EngineClient:
    def __init__(self, config: EngineClientConfig) -> None:
        if not isinstance(config, EngineClientConfig):
            raise TypeError("config must be EngineClientConfig")
        self.config = config

    def _seal(self) -> str:
        seal = mint_seal(
            self.config.service_principal,
            ttl_secs=max(30, int(self.config.timeout_seconds * 3)),
            secret=self.config.seal_secret,
        )
        if not seal:
            raise EngineUnavailable("engine request seal is unavailable")
        return seal

    def _request_json_sync(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None,
        deadline: datetime | None,
    ) -> dict[str, Any]:
        remaining = _deadline_remaining(deadline)
        timeout = self.config.timeout_seconds
        if remaining is not None:
            timeout = max(0.001, min(timeout, remaining))
        payload = None
        headers = {
            "Accept": "application/json",
            "x-gf-seal": self._seal(),
            "x-request-id": uuid4().hex,
        }
        if body is not None:
            payload = json.dumps(
                dict(body),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.config.base_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise EngineUnavailable(
                        "engine response exceeded size limit"
                    )
                decoded = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read(256 * 1024)
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"detail": "engine request failed"}
            if exc.code == 409:
                raise EngineRequestConflict(
                    str(detail.get("detail") or "engine conflict")
                ) from exc
            if exc.code in {401, 403}:
                raise EngineUnavailable(
                    "engine service authorization failed"
                ) from exc
            if exc.code == 404:
                raise EngineClientError("engine execution not found") from exc
            if exc.code in {422, 400}:
                raise EngineClientError(
                    str(detail.get("detail") or "engine request invalid")
                ) from exc
            raise EngineUnavailable(
                f"engine returned HTTP {exc.code}"
            ) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            OSError,
        ) as exc:
            raise EngineUnavailable("engine transport unavailable") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EngineUnavailable("engine returned malformed JSON") from exc
        if not isinstance(decoded, dict):
            raise EngineUnavailable("engine returned non-object JSON")
        return decoded

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        deadline: datetime | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        attempts = self.config.retry_attempts if retry else 1
        last: Exception | None = None
        for attempt in range(attempts):
            _deadline_remaining(deadline)
            try:
                return await asyncio.to_thread(
                    self._request_json_sync,
                    method,
                    path,
                    body=body,
                    deadline=deadline,
                )
            except EngineRequestConflict:
                raise
            except EngineDeadlineExceeded:
                raise
            except EngineUnavailable as exc:
                last = exc
                if attempt + 1 >= attempts:
                    break
                remaining = _deadline_remaining(deadline)
                sleep_for = min(
                    self.config.poll_interval_seconds
                    * (2 ** attempt),
                    1.0,
                )
                if remaining is not None:
                    sleep_for = min(sleep_for, remaining)
                await asyncio.sleep(max(0.001, sleep_for))
        assert last is not None
        raise last

    async def submit(
        self,
        command: EngineExecutionCommand,
        *,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError("command must be EngineExecutionCommand")
        return await self._request_json(
            "POST",
            "/api/v1/engine/executions",
            body={
                "actor_id": command.operation.actor_id,
                "tenant_id": command.operation.tenant_id,
                "command": command.as_dict(),
            },
            deadline=deadline,
            retry=True,
        )

    async def status(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {
                "actor_id": str(actor_id).strip(),
                "tenant_id": str(tenant_id).strip(),
            }
        )
        return await self._request_json(
            "GET",
            "/api/v1/engine/executions/" + execution_id + "?" + query,
            deadline=deadline,
            retry=True,
        )

    async def events(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {
                "actor_id": str(actor_id).strip(),
                "tenant_id": str(tenant_id).strip(),
            }
        )
        return await self._request_json(
            "GET",
            (
                "/api/v1/engine/executions/"
                + execution_id
                + "/events?"
                + query
            ),
            deadline=deadline,
            retry=True,
        )

    async def pending_tool_approvals(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        deadline: datetime | None = None,
    ) -> tuple[dict[str, str], ...]:
        actor = str(actor_id).strip()
        tenant = str(tenant_id).strip()
        if not actor or not tenant:
            raise EngineClientError(
                "actor_id and tenant_id are required for tool approval lookup"
            )
        query = urllib.parse.urlencode(
            {"actor_id": actor, "tenant_id": tenant}
        )
        payload = await self._request_json(
            "GET",
            (
                "/api/v1/engine/executions/"
                + execution_id
                + "/tool-approvals/pending?"
                + query
            ),
            deadline=deadline,
            retry=True,
        )
        rows = payload.get("pending")
        if not isinstance(rows, list):
            raise EngineUnavailable(
                "engine pending tool approval response is malformed"
            )
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise EngineUnavailable(
                    "engine pending tool approval row is malformed"
                )
            call_id = str(row.get("call_id") or "").strip()
            tool_id = str(row.get("tool_id") or "").strip()
            digest = str(row.get("arguments_digest") or "").strip()
            if (
                not call_id
                or not tool_id
                or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise EngineUnavailable(
                    "engine pending tool approval identity is malformed"
                )
            normalized.append(
                {
                    "call_id": call_id,
                    "tool_id": tool_id,
                    "arguments_digest": digest,
                }
            )
        return tuple(normalized)

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
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise EngineClientError(
                "tool approval expires_at must be timezone-aware"
            )
        body = {
            "actor_id": str(actor_id).strip(),
            "tenant_id": str(tenant_id).strip(),
            "call_id": str(call_id).strip(),
            "tool_id": str(tool_id).strip(),
            "arguments_digest": str(arguments_digest).strip(),
            "idempotency_key": str(idempotency_key).strip(),
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        }
        if any(
            not body[key]
            for key in (
                "actor_id",
                "tenant_id",
                "call_id",
                "tool_id",
                "idempotency_key",
            )
        ):
            raise EngineClientError(
                "tool approval identity fields must be non-empty"
            )
        digest = body["arguments_digest"]
        if (
            len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise EngineClientError(
                "tool approval arguments_digest must be lowercase sha256"
            )
        return await self._request_json(
            "POST",
            (
                "/api/v1/engine/executions/"
                + execution_id
                + "/tool-approvals"
            ),
            body=body,
            deadline=deadline,
            retry=True,
        )

    async def cancel(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        reason: str,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(reason, str) or not reason.strip():
            raise EngineClientError("cancellation reason is required")
        return await self._request_json(
            "POST",
            "/api/v1/engine/executions/" + execution_id + "/cancel",
            body={
                "actor_id": str(actor_id).strip(),
                "tenant_id": str(tenant_id).strip(),
                "reason": reason.strip(),
            },
            deadline=deadline,
            retry=True,
        )

    async def wait_for_result(
        self,
        execution_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        deadline: datetime,
    ) -> dict[str, Any]:
        while True:
            current = await self.status(
                execution_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                deadline=deadline,
            )
            state = str(current.get("operation_state") or "")
            if state in {"failed", "cancelled"}:
                raise EngineExecutionFailed(
                    "engine execution " + state,
                    status=current,
                )
            if state == "waiting_for_user":
                raise EngineApprovalRequired(
                    "engine execution requires tool approval",
                    execution_id=execution_id,
                    status=current,
                )
            if state == "completed":
                snapshot = await self.events(
                    execution_id,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    deadline=deadline,
                )
                events = snapshot.get("events")
                if not isinstance(events, list):
                    raise EngineUnavailable(
                        "engine event snapshot is malformed"
                    )
                for event in reversed(events):
                    if (
                        isinstance(event, dict)
                        and event.get("type") == "execution.result"
                        and isinstance(event.get("result"), dict)
                    ):
                        result = dict(event["result"])
                        if result.get("status") != "completed":
                            raise EngineExecutionFailed(
                                "engine result is not successful",
                                status=current,
                            )
                        return result
                raise EngineUnavailable(
                    "engine completed without canonical result event"
                )
            remaining = _deadline_remaining(deadline)
            sleep_for = self.config.poll_interval_seconds
            if remaining is not None:
                sleep_for = min(sleep_for, remaining)
            await asyncio.sleep(max(0.001, sleep_for))

    async def execute(
        self,
        command: EngineExecutionCommand,
        *,
        deadline: datetime,
    ) -> dict[str, Any]:
        ack = await self.submit(command, deadline=deadline)
        execution_id = str(
            ack.get("execution_id")
            or command.execution_request.execution_id
        )
        return await self.wait_for_result(
            execution_id,
            actor_id=command.operation.actor_id,
            tenant_id=command.operation.tenant_id,
            deadline=deadline,
        )


def _stable_uuid(namespace: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, namespace + ":" + value))


def _provider_request_digest(request: ProviderRequest) -> str:
    tools = [
        tool.as_dict()
        for tool in provider_tool_definitions(request)
    ]
    payload = {
        "instructions": request.instructions,
        "prompt": request.prompt,
        "history": [
            {"role": item.role, "content": item.content}
            for item in request.history
        ],
        "max_output_tokens": request.max_output_tokens,
        "model": request.model,
        "data_class": request.data_class,
        "purpose": request.purpose,
        "tenant_id": request.tenant_id,
        "operation_id": request.operation_id,
        "execution_id": request.execution_id,
        "turn_id": request.turn_id,
        "estimated_cost_usd": request.estimated_cost_usd,
        "resource_budget": request.resource_budget.as_dict(),
        "context_id": request.context_id,
        "context_digest": request.context_digest,
        "context_source_snapshot": [
            [segment_id, digest]
            for segment_id, digest in request.context_source_snapshot
        ],
        "context_compiler_version": request.context_compiler_version,
        "tools": tools,
        "structured_output_schema": (
            None
            if request.structured_output_schema is None
            else dict(request.structured_output_schema)
        ),
        "tool_choice": request.tool_choice,
        "specific_tool_id": request.specific_tool_id,
        "deadline": (
            None
            if request.deadline is None
            else request.deadline.astimezone(timezone.utc).isoformat()
        ),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def engine_command_from_provider_request(
    request: ProviderRequest,
    *,
    service_principal: str,
    actor_id: str = "backend-provider-compat",
    capability: str | None = None,
    idempotency_key: str | None = None,
    deadline: datetime | None = None,
) -> EngineExecutionCommand:
    """Wrap one neutral ProviderRequest as a canonical engine command.

    This is the migration seam for backend services that already speak the
    provider-neutral request contract but must no longer own provider
    credentials or provider network I/O.
    """

    if not isinstance(request, ProviderRequest):
        raise TypeError("request must be ProviderRequest")
    request_digest = _provider_request_digest(request)
    now = datetime.now(timezone.utc)
    effective_deadline = deadline or request.deadline
    if effective_deadline is None:
        effective_deadline = now + timedelta(
            seconds=float(request.resource_budget.max_wall_seconds)
        )
    if (
        effective_deadline.tzinfo is None
        or effective_deadline.utcoffset() is None
    ):
        raise EngineClientError("provider request deadline must be timezone-aware")
    effective_deadline = effective_deadline.astimezone(timezone.utc)
    if effective_deadline <= now:
        raise EngineDeadlineExceeded("engine deadline exceeded")

    raw_operation = str(request.operation_id or "").strip()
    try:
        operation_id = str(UUID(raw_operation))
    except (ValueError, AttributeError):
        operation_id = _stable_uuid(
            "skeleton-provider-operation",
            raw_operation or request_digest,
        )
    raw_execution = str(request.execution_id or "").strip()
    try:
        execution_id = str(UUID(raw_execution))
    except (ValueError, AttributeError):
        execution_id = _stable_uuid(
            "skeleton-provider-execution",
            raw_execution or (operation_id + ":" + request_digest),
        )
    raw_turn = str(request.turn_id or "").strip()
    try:
        turn_id = str(UUID(raw_turn))
    except (ValueError, AttributeError):
        turn_id = _stable_uuid(
            "skeleton-provider-turn",
            raw_turn or (execution_id + ":0"),
        )

    context_digest = request.context_digest or request_digest
    context_id = request.context_id or _stable_uuid(
        "skeleton-provider-context",
        context_digest,
    )
    if request.context_source_snapshot:
        source_snapshot = request.context_source_snapshot
    elif request.context_id is not None:
        raise EngineClientError(
            "provider request context_id requires immutable source snapshot"
        )
    else:
        source_snapshot = (
            (
                _stable_uuid(
                    "skeleton-provider-source",
                    request_digest,
                ),
                request_digest,
            ),
        )
    compiler_version = (
        request.context_compiler_version
        or "provider-compat/v1"
    )
    tenant_id = str(request.tenant_id or "default").strip()
    effective_capability = str(
        capability or ("provider." + request.purpose)
    ).strip()
    tools = provider_tool_definitions(request)

    handoff = EngineContextHandoff(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=tenant_id,
        context_id=context_id,
        context_digest=context_digest,
        compiler_version=compiler_version,
        source_snapshot=source_snapshot,
        data_class=request.data_class,
        purpose=request.purpose,
        instructions=request.instructions,
        prompt=request.prompt,
        history=tuple(
            (message.role, message.content)
            for message in request.history
        ),
        tools=tools,
        model=request.model,
        structured_output_schema=request.structured_output_schema,
        tool_choice=request.tool_choice,
        specific_tool_id=request.specific_tool_id,
        estimated_cost_usd=request.estimated_cost_usd,
    )
    budget = {
        **request.resource_budget.as_dict(),
        "max_model_turns": max(
            1,
            int(request.resource_budget.max_provider_attempts) + 1,
        ),
        "max_tool_calls": int(request.resource_budget.max_tool_calls),
        "max_output_tokens": int(
            request.max_output_tokens
            or request.resource_budget.max_output_tokens
        ),
        "max_elapsed_seconds": max(
            1,
            int(
                (
                    effective_deadline - now
                ).total_seconds()
            ),
        ),
    }
    operation = OperationEnvelope(
        operation_id=operation_id,
        tenant_id=tenant_id,
        actor_id=str(actor_id).strip(),
        capability=effective_capability,
        created_at=now,
        deadline=effective_deadline,
        idempotency_key=(
            str(idempotency_key).strip()
            if idempotency_key is not None
            else "provider:" + request_digest
        ),
        trace_id="provider-trace:" + request_digest[:32],
    )
    execution_request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective=request.prompt,
        context_policy={
            "tenant_id": tenant_id,
            "capability": effective_capability,
            "data_class": handoff.data_class,
            "provider_purpose": handoff.purpose,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "provider_model": handoff.model,
            "structured_output_schema": (
                None
                if handoff.structured_output_schema is None
                else dict(handoff.structured_output_schema)
            ),
            "tool_choice": handoff.tool_choice,
            "specific_tool_id": handoff.specific_tool_id,
            "estimated_cost_usd": handoff.estimated_cost_usd,
            "source_snapshot": [
                [segment_id, digest]
                for segment_id, digest in handoff.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": tenant_id,
            "allowed_tool_ids": [
                tool.tool_id for tool in tools
            ],
        },
        resource_budget=budget,
        stop_policy={
            "deadline": effective_deadline.isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=now,
    )
    authority = DelegatedAuthority(
        service_principal=str(service_principal).strip(),
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        ),
        capability=operation.capability,
        issued_at=now,
        expires_at=effective_deadline,
        request_binding=engine_request_binding(
            operation,
            execution_request,
        ),
    )
    return EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=tuple(
            "context-segment:" + segment_id
            for segment_id, _ in handoff.source_snapshot
        ),
        resource_budget=budget,
        stream_preferences={
            "mode": "events",
            "context_id": handoff.context_id,
        },
    )


def engine_command_from_context(
    *,
    context: ContextEnvelope,
    actor_id: str,
    capability: str,
    objective: str,
    idempotency_key: str,
    service_principal: str,
    deadline: datetime,
    max_model_turns: int = 6,
    max_tool_calls: int = 8,
    max_output_tokens: int = 4096,
) -> EngineExecutionCommand:
    """Build one canonical engine command from a compiled context snapshot."""

    if not isinstance(context, ContextEnvelope):
        raise TypeError("context must be ContextEnvelope")
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise EngineClientError("deadline must be timezone-aware")
    created_at = datetime.now(timezone.utc)
    operation = OperationEnvelope(
        operation_id=context.operation_id,
        tenant_id=context.tenant_id,
        actor_id=str(actor_id).strip(),
        capability=str(capability).strip(),
        created_at=created_at,
        deadline=deadline.astimezone(timezone.utc),
        idempotency_key=str(idempotency_key).strip(),
        trace_id=str(uuid4()),
    )
    provider_seed = provider_request_from_context(
        context,
        purpose="model-inference",
        max_output_tokens=max_output_tokens,
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
        data_class=provider_seed.data_class,
        purpose=provider_seed.purpose,
        instructions=provider_seed.instructions,
        prompt=provider_seed.prompt,
        history=tuple(
            (message.role, message.content)
            for message in provider_seed.history
        ),
        tools=provider_seed.tools,
        model=provider_seed.model,
        structured_output_schema=provider_seed.structured_output_schema,
        tool_choice=provider_seed.tool_choice,
        specific_tool_id=provider_seed.specific_tool_id,
        estimated_cost_usd=provider_seed.estimated_cost_usd,
    )

    budget = {
        "max_model_turns": int(max_model_turns),
        "max_tool_calls": int(max_tool_calls),
        "max_output_tokens": int(max_output_tokens),
        "max_elapsed_seconds": max(
            1,
            int((deadline - created_at).total_seconds()),
        ),
    }
    execution_request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=context.execution_id,
        objective=str(objective).strip(),
        context_policy={
            "tenant_id": context.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "provider_purpose": handoff.purpose,
            "context_id": context.context_id,
            "context_digest": context.context_digest,
            "compiler_version": context.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "provider_model": handoff.model,
            "structured_output_schema": (
                None
                if handoff.structured_output_schema is None
                else dict(handoff.structured_output_schema)
            ),
            "tool_choice": handoff.tool_choice,
            "specific_tool_id": handoff.specific_tool_id,
            "estimated_cost_usd": handoff.estimated_cost_usd,
            "source_snapshot": [
                [segment_id, digest]
                for segment_id, digest in context.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": context.tenant_id,
            "allowed_tool_ids": [
                tool.tool_id for tool in handoff.tools
            ],
        },
        resource_budget=budget,
        stop_policy={
            "deadline": deadline.astimezone(timezone.utc).isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=created_at,
    )
    authority = DelegatedAuthority(
        service_principal=str(service_principal).strip(),
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        ),
        capability=operation.capability,
        issued_at=created_at,
        expires_at=deadline.astimezone(timezone.utc),
        request_binding=engine_request_binding(
            operation,
            execution_request,
        ),
    )
    seed_refs = tuple(
        "context-segment:" + segment_id
        for segment_id, _ in context.source_snapshot
    )
    return EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=seed_refs,
        resource_budget=budget,
        stream_preferences={
            "mode": "events",
            "context_id": context.context_id,
        },
    )


__all__ = [
    "EngineApprovalRequired",
    "EngineClient",
    "EngineClientConfig",
    "EngineClientError",
    "EngineDeadlineExceeded",
    "EngineExecutionFailed",
    "EngineRequestConflict",
    "EngineUnavailable",
    "engine_command_from_context",
    "engine_command_from_provider_request",
]
