"""
routes/feature_flags.py — REST surface for the dynamic feature-flag service.

Surface (all under /api):

    GET    /feature-flags                          → list resolved flags
    GET    /feature-flags/{name}                   → flag detail
    POST   /feature-flags/{name}                   → upsert (admin)
    DELETE /feature-flags/{name}                   → delete (admin)
    POST   /feature-flags/bulk                     → bulk upsert (admin)
    GET    /feature-flags/health                   → service health
    GET    /feature-flags/audit                    → recent mutation audit log
    GET    /feature-flags/metrics                  → Prom + impression stats
    POST   /feature-flags/impressions              → analytics batch ingest

Best-practice middleware in this module:

  * ETag / If-None-Match on list endpoint (304 saves bandwidth).
  * Server-Timing header so devtools shows resolve+db split.
  * Per-IP rate-limit (10/min) on admin mutations.
  * Audit log on every upsert/delete (ip + ua + actor).
  * Admin gating via X-Admin-Token vs FEATURE_FLAGS_ADMIN_TOKEN.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core import feature_flags as ff
from core import feature_flags_audit as audit
from core import feature_flags_metrics as metrics

router = APIRouter(tags=["FeatureFlags"], prefix="/feature-flags")

# ─────────────────────────────────────────────────────────────────────
# Admin gating + rate-limiter
# ─────────────────────────────────────────────────────────────────────
ADMIN_TOKEN_ENV = "FEATURE_FLAGS_ADMIN_TOKEN"
RATE_LIMIT_PER_MIN = int(os.environ.get("FEATURE_FLAGS_ADMIN_RPM", "10"))
_rl_bucket: dict[str, deque] = defaultdict(deque)
# Lazy-init Lock to avoid event-loop binding crashes in production K8s.
_rl_lock: asyncio.Lock | None = None

def _get_rl_lock() -> asyncio.Lock:
    global _rl_lock
    if _rl_lock is None:
        _rl_lock = asyncio.Lock()
    return _rl_lock


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(request.client, "host", "") or "unknown"


async def _rate_limit(request: Request) -> None:
    """Per-IP sliding-window rate-limit for admin mutations."""
    ip = _client_ip(request)
    now = time.time()
    window = 60.0
    async with _get_rl_lock():
        q = _rl_bucket[ip]
        while q and (now - q[0]) > window:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            raise HTTPException(status_code=429, detail="rate_limited")
        q.append(now)


def _check_admin(token: str | None) -> None:
    expected = os.environ.get(ADMIN_TOKEN_ENV)
    if not expected:
        return       # dev mode — open
    if token != expected:
        raise HTTPException(status_code=403, detail="admin token required")


def _ua_of(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:200]


class FlagUpsert(BaseModel):
    enabled: bool | None = None
    rollout: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    environments: list[str] | None = None
    overrides: dict[str, bool] | None = None


class BulkUpsertRow(FlagUpsert):
    name: str


class BulkUpsertBody(BaseModel):
    flags: list[BulkUpsertRow]


class ImpressionRow(BaseModel):
    name: str
    value: bool
    count: int | None = 1
    ts: int | None = None


class ImpressionsBody(BaseModel):
    rows: list[ImpressionRow]


# ─────────────────────────────────────────────────────────────────────
# Reads
# ─────────────────────────────────────────────────────────────────────
@router.get("")
async def list_flags(
    request: Request,
    response: Response,
    user_id: str | None = Query(default=None),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> Any:
    t0 = time.perf_counter()
    # ETag built off (cache version, env, user_id, admin flag).
    is_admin = bool(os.environ.get(ADMIN_TOKEN_ENV)) and (x_admin_token == os.environ.get(ADMIN_TOKEN_ENV))
    # NB: when the env var isn't set we treat the caller as admin for fields
    # purposes (dev mode) — matches the mutation-gating behaviour.
    admin_view = is_admin or not os.environ.get(ADMIN_TOKEN_ENV)
    version = ff.cache_version()
    etag = f'W/"ff-v{version}-u{user_id or "_"}-a{int(admin_view)}"'

    if if_none_match and if_none_match == etag:
        response.status_code = 304
        response.headers["ETag"] = etag
        return Response(status_code=304, headers={"ETag": etag})

    flags = await ff.list_flags(user_id=user_id, include_admin_fields=admin_view)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["Server-Timing"] = f"ff_list;dur={dt_ms:.2f}"
    return {
        "ok": True,
        "environment": ff.ENVIRONMENT,
        "user_id": user_id,
        "version": version,
        "flags": flags,
    }


@router.get("/health")
async def flag_health() -> dict[str, Any]:
    return await ff.health()


@router.get("/metrics")
async def flag_metrics() -> dict[str, Any]:
    return {
        "ok": True,
        **(await metrics.stats()),
        "prom_lines": metrics.prom_lines()[:50],   # cap response size
    }


@router.get("/audit")
async def flag_audit(
    limit: int = Query(default=100, ge=1, le=500),
    name: str | None = Query(default=None),
) -> dict[str, Any]:
    rows = await audit.recent(limit=limit, name=name)
    stats = await audit.stats()
    return {"ok": True, "stats": stats, "rows": rows}


@router.get("/{name}")
async def get_flag(name: str) -> dict[str, Any]:
    doc = await ff.get_flag(name)
    if not doc:
        raise HTTPException(status_code=404, detail="flag not found")
    doc = dict(doc)
    doc.pop("_id", None)
    return {"ok": True, "flag": doc}


# ─────────────────────────────────────────────────────────────────────
# Mutations
# ─────────────────────────────────────────────────────────────────────
@router.post("/bulk")
async def bulk_upsert(
    request: Request,
    body: BulkUpsertBody,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    _check_admin(x_admin_token)
    await _rate_limit(request)
    updates = [r.model_dump(exclude_unset=True) for r in body.flags]
    n = await ff.bulk_upsert(updates)
    for u in updates:
        await audit.log_change(
            name=str(u.get("name") or ""),
            action="upsert", diff={"bulk": True, "fields": list(u.keys())},
            ip=_client_ip(request), user_agent=_ua_of(request), actor=x_actor,
        )
    return {"ok": True, "applied": n}


@router.post("/impressions")
async def post_impressions(body: ImpressionsBody) -> dict[str, Any]:
    added = await metrics.add_impression_batch([r.model_dump() for r in body.rows])
    return {"ok": True, "accepted": added}


@router.post("/{name}")
async def upsert_flag(
    request: Request,
    name: str,
    payload: FlagUpsert,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    _check_admin(x_admin_token)
    await _rate_limit(request)

    before = await ff.get_flag(name)
    doc = await ff.upsert_flag(
        name,
        enabled=payload.enabled,
        rollout=payload.rollout,
        description=payload.description,
        environments=payload.environments,
        overrides=payload.overrides,
    )
    diff: dict[str, Any] = {}
    payload_dict = payload.model_dump(exclude_unset=True)
    for k, v in payload_dict.items():
        prev = (before or {}).get(k)
        if prev != v:
            diff[k] = {"from": prev, "to": v}
    await audit.log_change(
        name=name, action="upsert", diff=diff,
        ip=_client_ip(request), user_agent=_ua_of(request),
        actor=x_actor,
    )
    if isinstance(doc, dict): doc.pop("_id", None)
    return {"ok": True, "flag": doc}


@router.delete("/{name}")
async def delete_flag(
    request: Request,
    name: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    _check_admin(x_admin_token)
    await _rate_limit(request)
    before = await ff.get_flag(name)
    ok = await ff.delete_flag(name)
    if ok and before:
        await audit.log_change(
            name=name, action="delete", diff={"deleted": True},
            ip=_client_ip(request), user_agent=_ua_of(request),
            actor=x_actor,
        )
    return {"ok": ok}
