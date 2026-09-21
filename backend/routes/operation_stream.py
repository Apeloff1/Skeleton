"""Authenticated HTTP/SSE adapter for canonical durable AI operations."""

from __future__ import annotations

import asyncio
from functools import lru_cache
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.operation_stream_transport import (
    OperationAccessDenied,
    OperationStreamTransport,
    OperationTransportConflict,
    StreamReplayGapError,
    encode_sse_event,
    encode_sse_heartbeat,
    transport_from_env,
)
from routes.gameforge_auth import require_role


router = APIRouter(prefix="/operations", tags=["AI Operations"])


def _positive_float_env(name: str, default: float, *, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < minimum:
        return default
    return value


_POLL_SECONDS = _positive_float_env(
    "CODEDOCK_OPERATION_STREAM_POLL_SECONDS",
    0.25,
    minimum=0.05,
)
_HEARTBEAT_SECONDS = _positive_float_env(
    "CODEDOCK_OPERATION_STREAM_HEARTBEAT_SECONDS",
    15.0,
    minimum=1.0,
)
_IDLE_TIMEOUT_SECONDS = _positive_float_env(
    "CODEDOCK_OPERATION_STREAM_IDLE_TIMEOUT_SECONDS",
    300.0,
    minimum=5.0,
)
_CONSUMER_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"
_CONSUMER_LEASE_SECONDS = 300


class OperationAckRequest(BaseModel):
    consumer_id: str = Field(min_length=1, max_length=128, pattern=_CONSUMER_PATTERN)
    sequence: int = Field(ge=0)


@lru_cache(maxsize=1)
def _transport() -> OperationStreamTransport:
    return transport_from_env()


def _principal_tenant(user: Any) -> str:
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    tenant = user.get("tenant_id") or user.get("email")
    if not isinstance(tenant, str) or not tenant.strip():
        raise HTTPException(status_code=403, detail="Tenant identity is required")
    return tenant.strip()


def _last_event_sequence(
    request: Request,
    explicit: int | None,
) -> int:
    if explicit is not None:
        return explicit
    raw = request.headers.get("last-event-id")
    if raw is None or not raw.strip():
        return 0
    value = raw.strip()
    if not value.isascii() or not value.isdigit():
        raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer")
    sequence = int(value, 10)
    if sequence < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be non-negative")
    return sequence


def _map_transport_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OperationAccessDenied):
        return HTTPException(status_code=404, detail="Operation not found")
    if isinstance(exc, StreamReplayGapError):
        return HTTPException(
            status_code=409,
            detail={
                "error": "replay_gap",
                "resync_required": True,
            },
        )
    if isinstance(exc, OperationTransportConflict):
        return HTTPException(
            status_code=409,
            detail="Operation changed concurrently; retry",
        )
    return HTTPException(status_code=503, detail="Operation transport unavailable")


@router.get("/{operation_id}")
def operation_status(
    operation_id: str,
    user=Depends(require_role("viewer")),
) -> dict[str, Any]:
    tenant_id = _principal_tenant(user)
    try:
        operation = _transport().status(operation_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_transport_error(exc) from None
    return {"ok": True, "operation": operation.as_dict()}


@router.post("/{operation_id}/cancel")
def cancel_operation(
    operation_id: str,
    user=Depends(require_role("viewer")),
) -> dict[str, Any]:
    tenant_id = _principal_tenant(user)
    try:
        result = _transport().cancel(operation_id, tenant_id=tenant_id)
    except Exception as exc:
        raise _map_transport_error(exc) from None
    return {"ok": True, **result.as_dict()}


@router.get("/{operation_id}/events/replay")
def operation_event_replay(
    operation_id: str,
    consumer_id: str = Query(
        ...,
        min_length=1,
        max_length=128,
        pattern=_CONSUMER_PATTERN,
    ),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=1000),
    user=Depends(require_role("viewer")),
) -> dict[str, Any]:
    """Authenticated cursor replay for native clients and resync flows."""

    tenant_id = _principal_tenant(user)
    try:
        batch = _transport().replay(
            operation_id,
            tenant_id=tenant_id,
            after_sequence=after_sequence,
            limit=limit,
            consumer_id=consumer_id,
            consumer_lease_seconds=_CONSUMER_LEASE_SECONDS,
        )
    except Exception as exc:
        raise _map_transport_error(exc) from None
    return {"ok": True, **batch.as_dict()}


@router.post("/{operation_id}/events/ack")
def acknowledge_operation_events(
    operation_id: str,
    body: OperationAckRequest,
    user=Depends(require_role("viewer")),
) -> dict[str, Any]:
    """Advance one client cursor only after the client applied the events."""

    tenant_id = _principal_tenant(user)
    try:
        checkpoint = _transport().acknowledge(
            operation_id,
            tenant_id=tenant_id,
            consumer_id=body.consumer_id,
            sequence=body.sequence,
            consumer_lease_seconds=_CONSUMER_LEASE_SECONDS,
        )
    except Exception as exc:
        raise _map_transport_error(exc) from None
    return {"ok": True, "consumer": checkpoint.as_dict()}


@router.get("/{operation_id}/events")
async def operation_events(
    request: Request,
    operation_id: str,
    consumer_id: str = Query(
        ...,
        min_length=1,
        max_length=128,
        pattern=_CONSUMER_PATTERN,
    ),
    after_sequence: int | None = Query(default=None, ge=0),
    user=Depends(require_role("viewer")),
) -> StreamingResponse:
    """Replay and follow one tenant-owned canonical operation with SSE."""

    tenant_id = _principal_tenant(user)
    cursor = _last_event_sequence(request, after_sequence)
    transport = _transport()

    try:
        initial = transport.replay(
            operation_id,
            tenant_id=tenant_id,
            after_sequence=cursor,
            consumer_id=consumer_id,
            consumer_lease_seconds=_CONSUMER_LEASE_SECONDS,
        )
    except Exception as exc:
        raise _map_transport_error(exc) from None

    async def stream():
        nonlocal cursor, initial
        last_activity = time.monotonic()
        last_heartbeat = last_activity
        batch = initial

        while True:
            if await request.is_disconnected():
                return

            if batch.events:
                for event in batch.events:
                    yield encode_sse_event(event)
                    cursor = event.sequence
                    last_activity = time.monotonic()
                    last_heartbeat = last_activity

            if batch.terminal:
                return

            now = time.monotonic()
            if now - last_activity >= _IDLE_TIMEOUT_SECONDS:
                yield ": idle-timeout\n\n"
                return

            if now - last_heartbeat >= _HEARTBEAT_SECONDS:
                yield encode_sse_heartbeat()
                last_heartbeat = now

            await asyncio.sleep(_POLL_SECONDS)
            try:
                batch = transport.replay(
                    operation_id,
                    tenant_id=tenant_id,
                    after_sequence=cursor,
                    consumer_id=consumer_id,
                    consumer_lease_seconds=_CONSUMER_LEASE_SECONDS,
                )
            except StreamReplayGapError:
                # Once response headers are committed an HTTP 409 is no longer
                # possible. Emit a transport-level resync signal and close.
                yield (
                    "event: stream.resync_required\n"
                    'data: {"error":"replay_gap","resync_required":true}\n\n'
                )
                return
            except OperationAccessDenied:
                return
            except Exception:
                yield (
                    "event: stream.unavailable\n"
                    'data: {"error":"transport_unavailable"}\n\n'
                )
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


__all__ = [
    "router",
    "operation_event_replay",
    "acknowledge_operation_events",
    "_last_event_sequence",
    "_principal_tenant",
]
