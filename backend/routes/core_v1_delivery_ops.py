"""Backend core v1 — delivery log, DLQ, retry-policy and secrets-admin HTTP adapter.

Same auth/tenancy/error contract as ``routes.core_v1_webhooks`` (shares its
``_scope`` dependency and error handler). Not registered in
``core.routes_registry``; mounting is owned by Middleware.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from core.core_v1 import render
from core.core_v1.delivery_ops import DeliveryOps, render_attempt, render_policy
from core.core_v1.errors import conflict, validation
from core.core_v1.models import Scope
from core.core_v1.pagination import parse_limit
from core.core_v1_webhooks import CoreRuntime, get_runtime
from routes.core_v1_webhooks import _json_object, _scope

router = APIRouter(prefix="/api/v1/core", tags=["Backend Core v1 — delivery ops"])


def _ops() -> DeliveryOps:
    rt: CoreRuntime = get_runtime()
    if rt.ops is None:  # pragma: no cover - build_runtime always wires ops
        raise conflict("CORE.STORE.UNAVAILABLE", "delivery ops not wired")
    return rt.ops


async def _optional_object(request: Request) -> dict:
    raw = await request.body()
    if not raw.strip():
        return {}
    return await _json_object(request)


# ------------------------------------------------------------- delivery log
@router.get("/deliveries")
def list_deliveries(limit: str | None = Query(None), cursor: str | None = Query(None),
                    webhook_id: str | None = Query(None), event_id: str | None = Query(None),
                    status: str | None = Query(None), since: str | None = Query(None),
                    until: str | None = Query(None), time_field: str = Query("created_at"),
                    scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    page = ops.deliveries(scope, limit=parse_limit(limit), cursor=cursor, webhook_id=webhook_id,
                          event_id=event_id, status=status, since=since, until=until,
                          time_field=time_field)
    return page.as_dict(render.delivery)


@router.get("/events/{event_id}/deliveries")
def event_deliveries(event_id: str, limit: str | None = Query(None), cursor: str | None = Query(None),
                     status: str | None = Query(None), scope: Scope = Depends(_scope),
                     ops: DeliveryOps = Depends(_ops)):
    page = ops.deliveries(scope, limit=parse_limit(limit), cursor=cursor, event_id=event_id,
                          status=status)
    return page.as_dict(render.delivery)


@router.get("/attempts")
def list_attempts(limit: str | None = Query(None), cursor: str | None = Query(None),
                  webhook_id: str | None = Query(None), event_id: str | None = Query(None),
                  delivery_id: str | None = Query(None), outcome: str | None = Query(None),
                  since: str | None = Query(None), until: str | None = Query(None),
                  scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    page = ops.attempts(scope, limit=parse_limit(limit), cursor=cursor, webhook_id=webhook_id,
                        event_id=event_id, delivery_id=delivery_id, outcome=outcome,
                        since=since, until=until)
    return page.as_dict(render_attempt)


@router.get("/webhooks/{webhook_id}/attempts")
def webhook_attempts(webhook_id: str, limit: str | None = Query(None), cursor: str | None = Query(None),
                     outcome: str | None = Query(None), since: str | None = Query(None),
                     until: str | None = Query(None), scope: Scope = Depends(_scope),
                     ops: DeliveryOps = Depends(_ops)):
    page = ops.attempts(scope, limit=parse_limit(limit), cursor=cursor, webhook_id=webhook_id,
                        outcome=outcome, since=since, until=until)
    return page.as_dict(render_attempt)


# --------------------------------------------------------------------- DLQ
@router.get("/dlq")
def list_dlq(limit: str | None = Query(None), cursor: str | None = Query(None),
             webhook_id: str | None = Query(None), since: str | None = Query(None),
             until: str | None = Query(None), scope: Scope = Depends(_scope),
             ops: DeliveryOps = Depends(_ops)):
    page = ops.dlq(scope, limit=parse_limit(limit), cursor=cursor, webhook_id=webhook_id,
                   since=since, until=until)
    return page.as_dict(render.delivery)


@router.post("/dlq/redrive", status_code=202)
async def redrive(request: Request, scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    body = await _json_object(request)
    return JSONResponse(ops.redrive(scope, body).as_dict(), status_code=202)


@router.post("/dlq/purge")
async def purge(request: Request, scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    return ops.purge(scope, await _json_object(request))


# ------------------------------------------------------------ retry policy
@router.get("/webhooks/{webhook_id}/retry-policy")
def get_policy(webhook_id: str, scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    policy, override = ops.get_policy(scope, webhook_id)
    return render_policy(policy, webhook_id, override)


@router.put("/webhooks/{webhook_id}/retry-policy")
async def put_policy(webhook_id: str, request: Request, scope: Scope = Depends(_scope),
                     ops: DeliveryOps = Depends(_ops)):
    body = await _json_object(request)
    return render_policy(ops.put_policy(scope, webhook_id, body), webhook_id, True)


@router.delete("/webhooks/{webhook_id}/retry-policy", status_code=204)
def delete_policy(webhook_id: str, scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    ops.delete_policy(scope, webhook_id)
    return Response(status_code=204)


# ----------------------------------------------------------- secrets admin
@router.get("/admin/secrets/status")
def secrets_status(scope: Scope = Depends(_scope), ops: DeliveryOps = Depends(_ops)):
    return ops.secrets_status(scope)


@router.post("/admin/secrets/encrypt")
async def secrets_encrypt(request: Request, scope: Scope = Depends(_scope),
                          ops: DeliveryOps = Depends(_ops)):
    return ops.secrets_job(scope, "encrypt", await _optional_object(request))


@router.post("/admin/secrets/rewrap")
async def secrets_rewrap(request: Request, scope: Scope = Depends(_scope),
                         ops: DeliveryOps = Depends(_ops)):
    return ops.secrets_job(scope, "rewrap", await _optional_object(request))


__all__ = ["router"]
