"""
telemetry.py — Modal-level telemetry + security observability endpoints.

Frontend posts batched events from useModalLogger() into a bounded in-memory
ring buffer; critical events are mirrored to Mongo for longer-term recall.

In production-like environments, telemetry ingestion requires an authenticated
viewer and telemetry/security reads require an admin. Local development keeps
the existing open workflow through the shared GameForge auth policy.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from core.databases import client as _SHARED_MONGO_CLIENT
from core.telemetry_privacy import (
    crash_metadata, safe_detail, safe_event, safe_label, safe_number, safe_session,
)
from middleware.security import AuditMiddleware, RateLimitMiddleware
from routes.gameforge_auth import require_role

_MAX_TELEMETRY_BODY_BYTES = 512 * 1024
_MAX_TELEMETRY_BATCH = 100


class _BoundedTelemetryRoute(APIRoute):
    """Reject oversized request bodies before FastAPI JSON parsing.

    A dependency runs too late: FastAPI has already fully materialized and
    validated the JSON before resolving dependencies. This route boundary
    enforces the byte budget at the ASGI receive stream instead.
    """

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            if request.method == "POST":
                header = request.headers.get("content-length")
                if header is not None:
                    try:
                        length = int(header)
                    except ValueError:
                        raise HTTPException(400, "Invalid content length") from None
                    if length < 0:
                        raise HTTPException(400, "Invalid content length")
                    if length > _MAX_TELEMETRY_BODY_BYTES:
                        raise HTTPException(413, "Telemetry request exceeds byte limit")
                collected = bytearray()
                async for chunk in request.stream():
                    if len(collected) + len(chunk) > _MAX_TELEMETRY_BODY_BYTES:
                        raise HTTPException(413, "Telemetry request exceeds byte limit")
                    collected.extend(chunk)
                # Starlette's cached request-body path permits the normal
                # FastAPI parser to read the already-admitted bytes.
                request._body = bytes(collected)
            return await handler(request)

        return guarded


router = APIRouter(route_class=_BoundedTelemetryRoute)

_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT
    return _client[_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# In-memory ring (avoids DB writes for high-frequency events)
# ─────────────────────────────────────────────────────────────────
_EVENT_RING: deque[dict] = deque(maxlen=10_000)
# Lazy-init Lock to avoid event-loop binding crashes in production K8s.
_RING_LOCK: asyncio.Lock | None = None


def _get_ring_lock() -> asyncio.Lock:
    global _RING_LOCK
    if _RING_LOCK is None:
        _RING_LOCK = asyncio.Lock()
    return _RING_LOCK


# ─────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────
class TelemetryEvent(BaseModel):
    modal_id: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=80)
    event: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "warn", "error", "fatal"] = "info"
    detail: Any | None = None
    ts_client: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration_ms: float | None = Field(default=None, ge=0, le=86_400_000, allow_inf_nan=False)


class TelemetryBatch(BaseModel):
    events: list[TelemetryEvent] = Field(min_length=1, max_length=_MAX_TELEMETRY_BATCH)


class CrashReport(BaseModel):
    source: str = Field(default="ErrorBoundary", max_length=80)
    component: str | None = Field(default=None, max_length=120)
    message: str = Field(max_length=2000)
    stack: str | None = Field(default=None, max_length=16_384)
    info: Any | None = None
    session_id: str | None = Field(default=None, max_length=80)
    app_version: str | None = Field(default=None, max_length=80)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
async def _persist_critical(event: dict) -> None:
    """Mirror errors + crashes to Mongo for longer-term recall.

    Motor.insert_one() mutates the input dict in-place by adding `_id`. The ring
    buffer holds the same dict reference, so persist a shallow copy instead.
    """
    if (
        event.get("severity") not in ("error", "fatal")
        and event.get("event") != "crash"
    ):
        return
    try:
        await _db().telemetry_critical.insert_one({**event})
    except Exception:
        pass  # never let logging break the request


def _norm(event: TelemetryEvent) -> dict:
    return {
        "ts": time.time(),
        "modal_id": safe_label(event.modal_id),
        "session_id": safe_session(event.session_id),
        "event": safe_event(event.event),
        "severity": event.severity if event.severity in {
            "info", "warn", "error", "fatal"
        } else "info",
        "ts_client": safe_number(event.ts_client, maximum=10_000_000_000),
        "duration_ms": safe_number(event.duration_ms, maximum=86_400_000),
        "detail": safe_detail(event.detail),
    }


# ─────────────────────────────────────────────────────────────────
# Ingest — authenticated viewer in enforced environments
# ─────────────────────────────────────────────────────────────────
@router.post(
    "/telemetry/event",
    dependencies=[Depends(require_role("viewer"))],
)
async def post_event(event: TelemetryEvent):
    row = _norm(event)
    async with _get_ring_lock():
        _EVENT_RING.append(row)
    await _persist_critical(row)
    return {"ok": True}


@router.post(
    "/telemetry/batch",
    dependencies=[Depends(require_role("viewer"))],
)
async def post_batch(batch: TelemetryBatch):
    rows = [_norm(event) for event in batch.events]
    async with _get_ring_lock():
        for row in rows:
            _EVENT_RING.append(row)
    # Persist critical ones outside the lock.
    for row in rows:
        await _persist_critical(row)
    return {"ok": True, "ingested": len(rows)}


def crash_row(report: CrashReport) -> dict:
    """Collect diagnostic presence and bounded safe scalars, never raw text."""
    return {
        "ts": time.time(),
        "modal_id": "__app__",
        "session_id": safe_session(report.session_id),
        "event": "crash",
        "severity": "fatal",
        "detail": crash_metadata(
            source=report.source,
            component=report.component,
            message=report.message,
            stack=report.stack,
            info=report.info,
            app_version=report.app_version,
        ),
    }


@router.post(
    "/telemetry/last-crash",
    dependencies=[Depends(require_role("viewer"))],
)
async def post_crash(report: CrashReport):
    row = crash_row(report)
    async with _get_ring_lock():
        _EVENT_RING.append(row)
    await _persist_critical(row)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Read — admin-only in enforced environments
# ─────────────────────────────────────────────────────────────────
@router.get(
    "/telemetry/critical/recent",
    dependencies=[Depends(require_role("admin"))],
)
async def telemetry_critical_recent(limit: int = 50):
    """Surface critical telemetry events without exposing them anonymously."""
    bounded_limit = max(1, min(limit, 200))
    rows = await _db().telemetry_critical.find({}, {"_id": 0}).to_list(bounded_limit)
    return {"events": rows, "count": len(rows)}


@router.get(
    "/telemetry/recent",
    dependencies=[Depends(require_role("admin"))],
)
async def recent(
    limit: int = 200,
    modal_id: str | None = None,
    severity: str | None = None,
    since_ts: float | None = None,
):
    rows = list(_EVENT_RING)
    if since_ts is not None:
        rows = [row for row in rows if row["ts"] >= since_ts]
    if modal_id:
        rows = [row for row in rows if row["modal_id"] == modal_id]
    if severity:
        rows = [row for row in rows if row["severity"] == severity]
    rows = rows[-max(1, min(limit, 2000)) :]
    return {"count": len(rows), "events": rows}


@router.get(
    "/telemetry/sessions",
    dependencies=[Depends(require_role("admin"))],
)
async def sessions(limit: int = 50):
    by_session: dict[str, dict] = {}
    for row in _EVENT_RING:
        session_id = row["session_id"]
        if session_id not in by_session:
            by_session[session_id] = {
                "session_id": session_id,
                "events": 0,
                "first_ts": row["ts"],
                "last_ts": row["ts"],
                "modals": set(),
                "errors": 0,
            }
        session = by_session[session_id]
        session["events"] += 1
        session["first_ts"] = min(session["first_ts"], row["ts"])
        session["last_ts"] = max(session["last_ts"], row["ts"])
        session["modals"].add(row["modal_id"])
        if row["severity"] in ("error", "fatal") or row["event"] == "crash":
            session["errors"] += 1

    bounded_limit = max(1, min(limit, 200))
    items = sorted(by_session.values(), key=lambda item: -item["last_ts"])[
        :bounded_limit
    ]
    for item in items:
        item["modal_count"] = len(item["modals"])
        item["modals"] = sorted(item["modals"])
        item["duration_s"] = round(item["last_ts"] - item["first_ts"], 1)
    return {"count": len(items), "sessions": items}


@router.get(
    "/telemetry/summary",
    dependencies=[Depends(require_role("admin"))],
)
async def summary():
    if not _EVENT_RING:
        return {"empty": True}
    by_modal: dict[str, int] = {}
    by_event: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    durations: list[float] = []
    errors = 0
    for row in _EVENT_RING:
        by_modal[row["modal_id"]] = by_modal.get(row["modal_id"], 0) + 1
        by_event[row["event"]] = by_event.get(row["event"], 0) + 1
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + 1
        if row["severity"] in ("error", "fatal") or row["event"] == "crash":
            errors += 1
        if row.get("duration_ms"):
            durations.append(float(row["duration_ms"]))
    return {
        "total_events": len(_EVENT_RING),
        "errors": errors,
        "error_rate": round(errors / max(len(_EVENT_RING), 1), 4),
        "top_modals": sorted(by_modal.items(), key=lambda item: -item[1])[:15],
        "by_event": by_event,
        "by_severity": by_severity,
        "avg_duration_ms": (
            round(sum(durations) / len(durations), 1) if durations else None
        ),
        "ring_capacity": _EVENT_RING.maxlen,
        "ring_size_now": len(_EVENT_RING),
    }


# ─────────────────────────────────────────────────────────────────
# Security observability — admin-only in enforced environments
# ─────────────────────────────────────────────────────────────────
@router.get(
    "/security/audit",
    dependencies=[Depends(require_role("admin"))],
)
async def audit(limit: int = 200, since_ts: float | None = None):
    return AuditMiddleware.snapshot(limit=limit, since_ts=since_ts)


@router.get(
    "/security/audit-summary",
    dependencies=[Depends(require_role("admin"))],
)
async def audit_summary():
    return AuditMiddleware.summary()


@router.get(
    "/security/rate-limits",
    dependencies=[Depends(require_role("admin"))],
)
async def rate_limits():
    return RateLimitMiddleware.snapshot()


@router.get(
    "/security/health",
    dependencies=[Depends(require_role("admin"))],
)
async def self_heal_health():
    """Composite administrative signal for backend self-heal diagnostics."""
    audit = AuditMiddleware.summary()
    error_rate = audit.get("error_rate", 0) if isinstance(audit, dict) else 0
    healthy = error_rate < 0.05
    return {
        "ok": healthy,
        "error_rate": error_rate,
        "audit_summary": audit,
        "rate_limit": RateLimitMiddleware.snapshot(),
        "telemetry_ring_size": len(_EVENT_RING),
        "ts": time.time(),
    }
