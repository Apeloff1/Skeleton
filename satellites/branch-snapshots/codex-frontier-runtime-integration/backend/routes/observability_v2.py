"""
routes/observability_v2.py — hardening + runtime health endpoints.

  GET /api/health/runtime  → full runtime snapshot (memory, GC, mongo,
                              tunnel, feature flags) — single call.
  GET /api/health/tunnel   → tunnel watchdog snapshot only.
  POST /api/telemetry/trail → ingest a frontend breadcrumb dump.
  GET /api/telemetry/trail  → recent trails (server-side ring).
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core import runtime_health, tunnel_watchdog

router = APIRouter(tags=["ObservabilityV2"])


# ── /api/health/runtime ────────────────────────────────────────────────
@router.get("/health/runtime")
async def health_runtime() -> dict[str, Any]:
    return await runtime_health.snapshot()


# ── /api/health/tunnel ────────────────────────────────────────────────
@router.get("/health/tunnel")
async def health_tunnel() -> dict[str, Any]:
    return tunnel_watchdog.snapshot()


# ── /api/telemetry/trail ──────────────────────────────────────────────
class TrailItem(BaseModel):
    ts: float
    category: str
    message: str
    level: str | None = None
    data: dict[str, Any] | None = None


class TrailDump(BaseModel):
    rid: str | None = None
    user_agent: str | None = None
    crumbs: list[TrailItem]


MAX_TRAILS = 200
_trails: deque[dict[str, Any]] = deque(maxlen=MAX_TRAILS)


@router.post("/telemetry/trail")
async def post_trail(body: TrailDump, request: Request) -> dict[str, Any]:
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
         or getattr(request.client, "host", "") or "unknown"
    entry = {
        "ts": time.time(),
        "ip": ip,
        "rid": body.rid,
        "ua": (body.user_agent or request.headers.get("user-agent") or "")[:200],
        "crumbs": [c.model_dump() for c in body.crumbs[-100:]],
    }
    _trails.append(entry)
    return {"ok": True, "buffered": len(_trails)}


@router.get("/telemetry/trail")
async def get_trail(limit: int = 25) -> dict[str, Any]:
    items = list(_trails)[-min(max(limit, 1), MAX_TRAILS):]
    return {"ok": True, "count": len(items), "trails": items}


# ── /api/telemetry/boot ─────────────────────────────────────────────────
class BootReport(BaseModel):
    ok: bool | None = None
    boot_score: float | None = None
    counts: dict[str, int] | None = None
    elapsed_ms: int | None = None
    stages: dict[str, Any] | None = None


MAX_BOOT_REPORTS = 200
_boot_reports: deque[dict[str, Any]] = deque(maxlen=MAX_BOOT_REPORTS)


@router.post("/telemetry/boot")
async def post_boot_report(body: BootReport, request: Request) -> dict[str, Any]:
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
         or getattr(request.client, "host", "") or "unknown"
    entry = {
        "ts": time.time(),
        "ip": ip,
        "ua": (request.headers.get("user-agent") or "")[:200],
        "ok": body.ok,
        "boot_score": body.boot_score,
        "counts": body.counts,
        "elapsed_ms": body.elapsed_ms,
        "stages_summary": (
            [{"id": k, "status": v.get("status"), "duration_ms": v.get("durationMs")}
             for k, v in (body.stages or {}).items()]
        ),
    }
    _boot_reports.append(entry)
    return {"ok": True, "buffered": len(_boot_reports)}


@router.get("/telemetry/boot")
async def get_boot_reports(limit: int = 25) -> dict[str, Any]:
    items = list(_boot_reports)[-min(max(limit, 1), MAX_BOOT_REPORTS):]
    # Roll-up: average boot score + p95 elapsed across the window.
    scores = [e["boot_score"] for e in items if isinstance(e.get("boot_score"), (int, float))]
    elapsed = sorted(e["elapsed_ms"] for e in items if isinstance(e.get("elapsed_ms"), int))
    avg_score = round(sum(scores) / len(scores), 2) if scores else None
    p95 = elapsed[int(len(elapsed) * 0.95) - 1] if elapsed else None
    return {
        "ok": True,
        "count": len(items),
        "avg_boot_score": avg_score,
        "p95_elapsed_ms": p95,
        "reports": items,
    }
