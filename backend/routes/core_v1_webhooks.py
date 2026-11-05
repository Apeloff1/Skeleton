"""Backend core v1 — webhooks HTTP adapter.

Not registered in ``core.routes_registry`` on purpose: mounting is owned by
Middleware (see docs/architecture/contracts/backend_core_v1.md).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from core.core_v1 import render
from core.core_v1.concurrency import etag
from core.core_v1.errors import CoreError, unauthenticated, validation
from core.core_v1.idempotency import StoredResponse, fingerprint
from core.core_v1.models import Scope, SubscriptionDraft
from core.core_v1.pagination import parse_limit
from core.core_v1_webhooks import CoreRuntime, get_runtime
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/api/v1/core", tags=["Backend Core v1"])
CREATE_FIELDS = {"url", "event_filters", "description", "max_attempts"}


def _scope(user: Any = Depends(get_current_user)) -> Scope:
    if not isinstance(user, dict) or user.get("dev_mode"):
        raise unauthenticated()
    actor = str(user.get("email") or user.get("user_id") or "").strip()
    if not actor or actor == "anonymous":
        raise unauthenticated()
    tenant = str(user.get("tenant_id") or "default").strip()
    return Scope(tenant_id=tenant, actor_id=actor, role=str(user.get("role") or "viewer"))


def _rt() -> CoreRuntime:
    return get_runtime()


def error_response(exc: CoreError) -> JSONResponse:
    headers = {}
    if exc.code == "CORE.CONCURRENCY.PRECONDITION_FAILED" and exc.context.get("current_etag"):
        headers["ETag"] = exc.context["current_etag"]
    return JSONResponse(exc.envelope(), status_code=exc.http_status, headers=headers)


def install_error_handler(app) -> None:
    app.add_exception_handler(CoreError, lambda _req, exc: error_response(exc))


async def _json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise validation("CORE.REQUEST.INVALID_JSON", "body must be valid JSON") from None
    if not isinstance(body, dict):
        raise validation("CORE.REQUEST.INVALID_JSON", "body must be a JSON object")
    return body


def _with_etag(body: dict, status: int = 200, replayed: bool = False) -> JSONResponse:
    headers = {"ETag": body["etag"]} if "etag" in body else {}
    if replayed:
        headers["Idempotent-Replayed"] = "true"
    return JSONResponse(body, status_code=status, headers=headers)


def _idem(rt: CoreRuntime, scope: Scope, key: str | None, route: str, body: dict, action):
    fp = fingerprint("POST", route, body)
    resp, replayed = rt.idempotency.run(key, (scope.tenant_id, scope.actor_id, route), fp, action)
    return _with_etag(resp.body, resp.status, replayed)


@router.post("/webhooks", status_code=201)
async def create_webhook(request: Request, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt),
                         idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    body = await _json_object(request)

    def action() -> StoredResponse:
        extra = {k: v for k, v in body.items() if k not in CREATE_FIELDS}
        draft = SubscriptionDraft(url=body.get("url"), event_filters=tuple(body.get("event_filters") or ()),
                                  description=body.get("description", ""),
                                  max_attempts=body.get("max_attempts", 8), extra=extra)
        created = rt.webhooks.create(scope, draft)
        return StoredResponse(201, {**render.subscription(created.subscription), "secret": created.secret})

    return _idem(rt, scope, idempotency_key, "webhooks.create", body, action)


@router.get("/webhooks")
def list_webhooks(limit: str | None = Query(None), cursor: str | None = Query(None),
                  scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt)):
    page = rt.webhooks.list(scope, parse_limit(limit), cursor)
    return page.as_dict(render.subscription)


@router.get("/webhooks/{webhook_id}")
def get_webhook(webhook_id: str, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt)):
    return _with_etag(render.subscription(rt.webhooks.get(scope, webhook_id)))


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(webhook_id: str, request: Request, scope: Scope = Depends(_scope),
                         rt: CoreRuntime = Depends(_rt), if_match: str | None = Header(None, alias="If-Match")):
    patch = await _json_object(request)
    return _with_etag(render.subscription(rt.webhooks.update(scope, webhook_id, patch, if_match)))


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt),
                   if_match: str | None = Header(None, alias="If-Match")):
    return _with_etag(render.subscription(rt.webhooks.delete(scope, webhook_id, if_match)))


@router.post("/webhooks/{webhook_id}/rotate-secret")
def rotate_secret(webhook_id: str, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt),
                  if_match: str | None = Header(None, alias="If-Match")):
    created = rt.webhooks.rotate_secret(scope, webhook_id, if_match)
    return _with_etag({**render.subscription(created.subscription), "secret": created.secret})


@router.get("/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: str, limit: str | None = Query(None), cursor: str | None = Query(None),
                    status: str | None = Query(None), scope: Scope = Depends(_scope),
                    rt: CoreRuntime = Depends(_rt)):
    page = rt.webhooks.list_deliveries(scope, webhook_id, parse_limit(limit), cursor, status)
    return page.as_dict(render.delivery)


@router.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: str, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt)):
    d, attempts = rt.webhooks.get_delivery(scope, delivery_id)
    return {**render.delivery(d), "attempt_log": [render.attempt(a) for a in attempts]}


@router.post("/deliveries/{delivery_id}/replay", status_code=202)
def replay_delivery(delivery_id: str, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt),
                    idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    def action() -> StoredResponse:
        return StoredResponse(202, render.delivery(rt.webhooks.replay(scope, delivery_id)))
    return _idem(rt, scope, idempotency_key, f"deliveries.replay:{delivery_id}", {}, action)


@router.post("/events", status_code=202)
async def publish_event(request: Request, scope: Scope = Depends(_scope), rt: CoreRuntime = Depends(_rt)):
    body = await _json_object(request)
    unknown = set(body) - {"type", "data", "dedupe_key"}
    if unknown:
        raise validation("CORE.EVENT.INVALID", "unknown fields", fields=sorted(unknown))
    event, fanout, duplicate = rt.webhooks.publish(scope, body.get("type"), body.get("data"),
                                                   body.get("dedupe_key"))
    return JSONResponse({**render.event(event), "deliveries_created": fanout, "duplicate": duplicate},
                        status_code=200 if duplicate else 202)


__all__ = ["router", "install_error_handler", "error_response", "etag"]
