"""Realtime HTTP adapter: canonical SSE stream + presence (ADR PR #4101).

Mounted under ``/api/v1`` by ``skeleton.api.server.create_app``:

* ``GET  /api/v1/events?channels=build,agent,presence[&job_id=][&cursor=]``
  canonical multiplexed SSE stream. Resume with ``Last-Event-ID`` (preferred)
  or ``?cursor=``.
* ``POST /api/v1/presence`` body ``{action: join|heartbeat|leave, scope, client_id, meta?}``
* ``GET  /api/v1/presence?scope=`` current members.
* ``GET  /api/v1/events/slo`` realtime SLO snapshot + hub stats.

Auth reuses the existing gate: both prefixes are written gate domains, so the
``x-gf-seal`` HMAC seal is verified by ``RequestSealMiddleware`` and the
verified principal arrives as ``x-zaibatsu-attester`` (``AuthMiddleware``).
Handlers fail closed if that header is absent.

Authorization (Jenkins S1-1): without ``job_id`` a caller only receives
build/agent events whose hub-side owner is its own principal. With
``job_id`` the caller must pass ``actor_id`` + ``tenant_id`` and the engine
execution-events checks (service bearer token, verified attester,
``engine:events`` grant, actor/tenant ownership) run via
``engine_routes.authorize_execution_events`` before a job grant is issued.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from skeleton.realtime import CHANNELS, EnvelopeError, RealtimeAuthError, RealtimeHub, parse_cursor
from skeleton.realtime.guard import RealtimeSecretError
from skeleton.realtime.sse import SSE_MEDIA_TYPE, sse_body, sse_headers

router = APIRouter(tags=["realtime"])

_MAX_EVENTS_CAP = 10_000


def get_hub(app: Any) -> RealtimeHub:
    hub = getattr(getattr(app, "state", None), "realtime_hub", None)
    if hub is None:
        raise HTTPException(status_code=503, detail={"error": "realtime_unavailable"})
    return hub


def _principal(attester: Optional[str]) -> str:
    if not attester:
        raise HTTPException(status_code=401, detail={"error": "seal_required"})
    return attester


def _channels(raw: Optional[str]) -> tuple:
    if raw is None or not raw.strip():
        return CHANNELS
    wanted = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = [c for c in wanted if c not in CHANNELS]
    if unknown or not wanted:
        raise HTTPException(status_code=422, detail={"error": "unknown_channel", "channels": unknown, "allowed": list(CHANNELS)})
    return wanted


def _cursor(last_event_id: Optional[str], cursor: Optional[str]) -> Optional[int]:
    try:
        return parse_cursor(last_event_id) if last_event_id else parse_cursor(cursor)
    except EnvelopeError:
        raise HTTPException(status_code=422, detail={"error": "invalid_cursor"}) from None


def open_stream(
    request: Request,
    *,
    principal: str,
    channels: tuple,
    job_id: Optional[str],
    cursor: Optional[int],
    max_events: Optional[int] = None,
    job_grant: Optional[str] = None,
) -> StreamingResponse:
    """Subscribe and return the SSE response. Shared with filtered views."""
    hub = get_hub(request.app)
    try:
        sub = hub.subscribe(channels, principal=principal, cursor=cursor, job_id=job_id, job_grant=job_grant)
    except RealtimeAuthError:
        raise HTTPException(status_code=403, detail={"error": "channel_forbidden"}) from None
    except EnvelopeError as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_subscription", "reason": str(exc)}) from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail={"error": "realtime_unavailable"}) from None
    return StreamingResponse(
        sse_body(hub, sub, max_events=max_events, is_disconnected=request.is_disconnected),
        media_type=SSE_MEDIA_TYPE,
        headers=sse_headers(),
    )


def wants_event_stream(request: Request) -> bool:
    return SSE_MEDIA_TYPE in (request.headers.get("accept") or "").lower()


@router.get("/events")
async def events_stream(
    request: Request,
    channels: Optional[str] = Query(default=None, max_length=64),
    job_id: Optional[str] = Query(default=None, max_length=128),
    cursor: Optional[str] = Query(default=None, max_length=32),
    max_events: Optional[int] = Query(default=None, ge=1, le=_MAX_EVENTS_CAP),
    actor_id: Optional[str] = Query(default=None, min_length=1, max_length=512),
    tenant_id: Optional[str] = Query(default=None, min_length=1, max_length=512),
    last_event_id: Optional[str] = Header(default=None, alias="last-event-id"),
    attester: Optional[str] = Header(default=None, alias="x-zaibatsu-attester"),
) -> StreamingResponse:
    principal = _principal(attester)
    wanted = _channels(channels)
    parsed_cursor = _cursor(last_event_id, cursor)
    job_grant: Optional[str] = None
    if job_id is not None:
        if not actor_id or not tenant_id:
            raise HTTPException(status_code=422, detail={"error": "job_scope_required", "required": ["actor_id", "tenant_id"]})
        from skeleton.api.engine_routes import authorize_execution_events

        principal, _snapshot = authorize_execution_events(request, job_id, actor_id=actor_id, tenant_id=tenant_id)
        job_grant = job_id
    return open_stream(
        request,
        principal=principal,
        channels=wanted,
        job_id=job_id,
        cursor=parsed_cursor,
        max_events=max_events,
        job_grant=job_grant,
    )


@router.get("/events/slo")
async def events_slo(
    request: Request,
    attester: Optional[str] = Header(default=None, alias="x-zaibatsu-attester"),
) -> Dict[str, Any]:
    _principal(attester)
    hub = get_hub(request.app)
    return {"slo": hub.slo.snapshot(), "hub": hub.stats()}


class PresenceRequest(BaseModel):
    action: str = Field(..., pattern="^(join|heartbeat|leave)$")
    client_id: str = Field(..., min_length=1, max_length=128)
    scope: str = Field(default="app", min_length=1, max_length=128)
    meta: Dict[str, Any] = Field(default_factory=dict)


@router.post("/presence")
async def presence_action(
    body: PresenceRequest,
    request: Request,
    attester: Optional[str] = Header(default=None, alias="x-zaibatsu-attester"),
) -> Dict[str, Any]:
    principal = _principal(attester)
    hub = get_hub(request.app)
    try:
        return hub.presence(body.action, client_id=body.client_id, scope=body.scope, principal=principal, meta=body.meta)
    except RealtimeAuthError:
        raise HTTPException(status_code=403, detail={"error": "presence_forbidden"}) from None
    except (EnvelopeError, RealtimeSecretError) as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_presence", "reason": str(exc)}) from None


@router.get("/presence")
async def presence_snapshot(
    request: Request,
    scope: str = Query(default="app", min_length=1, max_length=128),
    attester: Optional[str] = Header(default=None, alias="x-zaibatsu-attester"),
) -> Dict[str, Any]:
    principal = _principal(attester)
    hub = get_hub(request.app)
    try:
        return hub.presence_snapshot(scope, principal=principal)
    except EnvelopeError:
        raise HTTPException(status_code=422, detail={"error": "invalid_scope"}) from None


def execution_stream_or_none(request: Request, execution_id: str, *, principal: str) -> Optional[StreamingResponse]:
    """SSE filtered view for ``GET /api/v1/engine/executions/{id}/events``.

    Returns ``None`` (caller keeps its JSON response) unless the client asked
    for ``text/event-stream`` and a hub is mounted. Caller must have already
    authorized access to ``execution_id`` (``authorize_execution_events``);
    the stream gets a job grant for exactly that id. An empty principal is
    denied (no shared fallback identity).
    """
    if not wants_event_stream(request):
        return None
    if getattr(getattr(request.app, "state", None), "realtime_hub", None) is None:
        return None
    if not principal:
        raise HTTPException(status_code=401, detail={"error": "seal_required"})
    return open_stream(
        request,
        principal=principal,
        channels=("build", "agent"),
        job_id=execution_id,
        job_grant=execution_id,
        cursor=_cursor(request.headers.get("last-event-id"), request.query_params.get("cursor")),
    )


__all__ = ["execution_stream_or_none", "get_hub", "open_stream", "router", "wants_event_stream"]
