"""Backend client for the canonical Skeleton cognitive-execution engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import socket
import time
from typing import Any, Mapping
import urllib.error
import urllib.request
from uuid import uuid4

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
from skeleton.provider_runtime import provider_request_from_context


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
            body={"command": command.as_dict()},
            deadline=deadline,
            retry=True,
        )

    async def status(
        self,
        execution_id: str,
        *,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            "/api/v1/engine/executions/" + execution_id,
            deadline=deadline,
            retry=True,
        )

    async def events(
        self,
        execution_id: str,
        *,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            "/api/v1/engine/executions/" + execution_id + "/events",
            deadline=deadline,
            retry=True,
        )

    async def cancel(
        self,
        execution_id: str,
        *,
        reason: str,
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(reason, str) or not reason.strip():
            raise EngineClientError("cancellation reason is required")
        return await self._request_json(
            "POST",
            "/api/v1/engine/executions/" + execution_id + "/cancel",
            body={"reason": reason.strip()},
            deadline=deadline,
            retry=True,
        )

    async def wait_for_result(
        self,
        execution_id: str,
        *,
        deadline: datetime,
    ) -> dict[str, Any]:
        while True:
            current = await self.status(execution_id, deadline=deadline)
            state = str(current.get("operation_state") or "")
            if state in {"failed", "cancelled"}:
                raise EngineExecutionFailed(
                    "engine execution " + state,
                    status=current,
                )
            if state == "completed":
                snapshot = await self.events(
                    execution_id,
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
            deadline=deadline,
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
        instructions=provider_seed.instructions,
        prompt=provider_seed.prompt,
        history=tuple(
            (message.role, message.content)
            for message in provider_seed.history
        ),
        tools=provider_seed.tools,
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
            "context_id": context.context_id,
            "context_digest": context.context_digest,
            "compiler_version": context.compiler_version,
            "handoff_digest": handoff.handoff_digest,
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
    "EngineClient",
    "EngineClientConfig",
    "EngineClientError",
    "EngineDeadlineExceeded",
    "EngineExecutionFailed",
    "EngineRequestConflict",
    "EngineUnavailable",
    "engine_command_from_context",
]
