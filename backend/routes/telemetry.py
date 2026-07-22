"""
telemetry.py — Modal-level telemetry + security observability endpoints.

Frontend posts batched events from useModalLogger() into a bounded in-memory
ring buffer; we mirror critical events to Mongo for longer-term recall.

Endpoints:
  POST /api/telemetry/event       — single event
  POST /api/telemetry/batch       — array of events (preferred from clients)
  GET  /api/telemetry/recent      — last N events (filter by modal_id, severity)
  GET  /api/telemetry/sessions    — group by session_id
  GET  /api/telemetry/summary     — aggregate counts/durations
  POST /api/telemetry/last-crash  — frontend ErrorBoundary posts caught error here

  GET  /api/security/audit        — backend request audit ring
  GET  /api/security/audit-summary
  GET  /api/security/rate-limits  — current bucket state
  GET  /api/security/health       — composite self-heal signals
"""
from __future__ import annotations
import os
import time
import asyncio
from collections import deque
from typing import Any, Deque, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

from middleware.security import AuditMiddleware, RateLimitMiddleware

router = APIRouter()


@router.get("/telemetry/critical/recent")
async def telemetry_critical_recent(limit: int = 50):
    """Surface critical telemetry events (telemetry_critical was written but never read)."""
    rows = await _db().telemetry_critical.find({}, {"_id": 0}).to_list(min(limit, 200))
    return {"events": rows, "count": len(rows)}

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# In-memory ring (avoids DB writes for high-frequency events)
# ─────────────────────────────────────────────────────────────────
_EVENT_RING: Deque[dict] = deque(maxlen=10_000)
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
    modal_id:   str   = Field(..., description="canonical modal/screen id, e.g. 'GalaxyStudioFactoryModal'")
    session_id: str   = Field(..., description="opaque per-app-launch session id from client")
    event:      str   = Field(..., description="open|close|action|error|nav|metric")
    severity:   str   = "info"
    detail:     Optional[Any] = None
    ts_client:  Optional[float] = None
    duration_ms: Optional[float] = None


class TelemetryBatch(BaseModel):
    events: List[TelemetryEvent]


class CrashReport(BaseModel):
    source:       str  = "ErrorBoundary"
    component:    Optional[str] = None
    message:      str
    stack:        Optional[str] = None
    info:         Optional[Any] = None
    session_id:   Optional[str] = None
    app_version:  Optional[str] = None


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
async def _persist_critical(event: dict) -> None:
    """Mirror errors + crashes to Mongo for longer-term recall.

    IMPORTANT: Motor.insert_one() mutates the input dict in-place by adding
    `_id: ObjectId(...)`. The ring buffer holds the same dict reference, so
    mutating it poisons subsequent /telemetry/recent reads (ObjectId is not
    JSON-serializable). We pass a shallow copy to prevent contamination.
    """
    if event.get("severity") not in ("error", "fatal") and event.get("event") != "crash":
        return
    try:
        await _db().telemetry_critical.insert_one({**event})
    except Exception:
        pass  # never let logging break the request


def _norm(event: TelemetryEvent) -> dict:
    return {
        "ts":          time.time(),
        "modal_id":    event.modal_id[:80],
        "session_id":  event.session_id[:40],
        "event":       event.event[:24],
        "severity":    event.severity[:16],
        "ts_client":   event.ts_client,
        "duration_ms": event.duration_ms,
        "detail":      event.detail,
    }


# ─────────────────────────────────────────────────────────────────
# Ingest
# ─────────────────────────────────────────────────────────────────
@router.post("/telemetry/event")
async def post_event(event: TelemetryEvent):
    row = _norm(event)
    async with _get_ring_lock():
        _EVENT_RING.append(row)
    await _persist_critical(row)
    return {"ok": True}


@router.post("/telemetry/batch")
async def post_batch(batch: TelemetryBatch):
    rows = [_norm(e) for e in batch.events[:500]]  # cap per batch
    async with _get_ring_lock():
        for r in rows:
            _EVENT_RING.append(r)
    # Persist critical ones outside the lock
    for r in rows:
        await _persist_critical(r)
    return {"ok": True, "ingested": len(rows)}


@router.post("/telemetry/last-crash")
async def post_crash(report: CrashReport):
    row = {
        "ts":          time.time(),
        "modal_id":    "__app__",
        "session_id":  (report.session_id or "anon")[:40],
        "event":       "crash",
        "severity":    "fatal",
        "detail": {
            "source":    report.source,
            "component": report.component,
            "message":   report.message,
            "stack":     (report.stack or "")[:8000],
            "info":      report.info,
            "app_version": report.app_version,
        },
    }
    async with _get_ring_lock():
        _EVENT_RING.append(row)
    await _persist_critical(row)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────
@router.get("/telemetry/recent")
async def recent(
    limit: int = 200,
    modal_id: str | None = None,
    severity: str | None = None,
    since_ts: float | None = None,
):
    rows = list(_EVENT_RING)
    if since_ts:
        rows = [r for r in rows if r["ts"] >= since_ts]
    if modal_id:
        rows = [r for r in rows if r["modal_id"] == modal_id]
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    rows = rows[-max(1, min(limit, 2000)):]
    return {"count": len(rows), "events": rows}


@router.get("/telemetry/sessions")
async def sessions(limit: int = 50):
    by_session: dict[str, dict] = {}
    for r in _EVENT_RING:
        s = r["session_id"]
        if s not in by_session:
            by_session[s] = {
                "session_id": s, "events": 0,
                "first_ts": r["ts"], "last_ts": r["ts"],
                "modals":   set(), "errors": 0,
            }
        d = by_session[s]
        d["events"] += 1
        d["first_ts"] = min(d["first_ts"], r["ts"])
        d["last_ts"]  = max(d["last_ts"],  r["ts"])
        d["modals"].add(r["modal_id"])
        if r["severity"] in ("error", "fatal") or r["event"] == "crash":
            d["errors"] += 1
    items = sorted(by_session.values(), key=lambda x: -x["last_ts"])[:limit]
    for x in items:
        x["modal_count"] = len(x["modals"])
        x["modals"] = sorted(x["modals"])
        x["duration_s"] = round(x["last_ts"] - x["first_ts"], 1)
    return {"count": len(items), "sessions": items}


@router.get("/telemetry/summary")
async def summary():
    if not _EVENT_RING:
        return {"empty": True}
    by_modal:    dict[str, int] = {}
    by_event:    dict[str, int] = {}
    by_severity: dict[str, int] = {}
    durations:   list[float] = []
    errors = 0
    for r in _EVENT_RING:
        by_modal[r["modal_id"]] = by_modal.get(r["modal_id"], 0) + 1
        by_event[r["event"]]    = by_event.get(r["event"], 0) + 1
        by_severity[r["severity"]] = by_severity.get(r["severity"], 0) + 1
        if r["severity"] in ("error", "fatal") or r["event"] == "crash":
            errors += 1
        if r.get("duration_ms"):
            durations.append(float(r["duration_ms"]))
    return {
        "total_events":   len(_EVENT_RING),
        "errors":         errors,
        "error_rate":     round(errors / max(len(_EVENT_RING), 1), 4),
        "top_modals":     sorted(by_modal.items(), key=lambda kv: -kv[1])[:15],
        "by_event":       by_event,
        "by_severity":    by_severity,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "ring_capacity":  _EVENT_RING.maxlen,
        "ring_size_now":  len(_EVENT_RING),
    }


# ─────────────────────────────────────────────────────────────────
# Security observability
# ─────────────────────────────────────────────────────────────────
@router.get("/security/audit")
async def audit(limit: int = 200, since_ts: float | None = None):
    return AuditMiddleware.snapshot(limit=limit, since_ts=since_ts)


@router.get("/security/audit-summary")
async def audit_summary():
    return AuditMiddleware.summary()


@router.get("/security/rate-limits")
async def rate_limits():
    return RateLimitMiddleware.snapshot()


@router.get("/security/health")
async def self_heal_health():
    """Composite signal the frontend can poll for a self-heal banner."""
    summary = AuditMiddleware.summary()
    error_rate = summary.get("error_rate", 0) if isinstance(summary, dict) else 0
    healthy = error_rate < 0.05  # < 5% error rate
    return {
        "ok": healthy,
        "error_rate": error_rate,
        "audit_summary": summary,
        "rate_limit": RateLimitMiddleware.snapshot(),
        "telemetry_ring_size": len(_EVENT_RING),
        "ts": time.time(),
    }
