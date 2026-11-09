"""
routes/galaxy_studio_watchdog.py — Watchdog / diagnose / resurrect /
force-advance sub-router.

Extracted from routes/galaxy_studio.py (Phase-4 decomposition, Feb 2026).
This is the SECOND cluster to use the ``galaxy_studio_state`` lazy proxy
pattern (Phase-3 prereq). All four endpoints below need shared build
state (``_builds``, ``_active_runners``) and three helper coroutines
(``_load_build``, ``_save_build``, ``_advance_build``) plus the
``_run_background_build`` task launcher from the parent module —
every one of those is now reachable via ``galaxy_studio_state`` without
incurring a circular import.

Public paths (UNCHANGED from before extraction):
  POST /api/galaxy-studio/resurrect/{build_id}
  GET  /api/galaxy-studio/watchdog/health
  GET  /api/galaxy-studio/diagnose/{build_id}
  POST /api/galaxy-studio/force-advance/{build_id}
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from routes.galaxy_studio_state import (
    _builds,
    _active_runners,
    TOTAL_BATCHES,
    load_build,
    save_build,
    advance_build,
    get_run_background_build,
)

router = APIRouter(tags=["galaxy-studio"])


@router.post("/resurrect/{build_id}")
async def resurrect_build(build_id: str, duration_minutes: int = 15) -> dict:
    """Force-restart the background runner for a stuck build. Safe to call
    repeatedly — if the runner is already active, returns ok without
    disturbing. Frontend calls this on first 404 or after 90 s without a
    phase advance."""
    import asyncio as _asyncio

    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found — cannot resurrect")
    if build.get("status") == "completed":
        return {"ok": True, "build_id": build_id, "status": "completed",
                "message": "already complete"}
    if build_id in _active_runners:
        return {"ok": True, "build_id": build_id, "status": "running",
                "message": "runner already active"}
    resume_from = max(1, int(build.get("_bg_current_batch", 0) or 0) + 1)
    if resume_from > TOTAL_BATCHES:
        build["status"] = "completed"
        build["_bg_status"] = "completed"
        await save_build(build)
        return {"ok": True, "build_id": build_id, "status": "completed",
                "message": "finalised"}
    _active_runners.add(build_id)
    runner = get_run_background_build()
    _asyncio.create_task(runner(build_id, duration_minutes,
                                resume_from_batch=resume_from))
    return {
        "ok": True, "build_id": build_id, "status": "resurrected",
        "resumed_from_batch": resume_from, "total_batches": TOTAL_BATCHES,
    }


@router.get("/watchdog/health")
async def watchdog_health() -> dict:
    """Diagnostic endpoint — returns watchdog scan counts, interval,
    and a snapshot of active-builds + runner sets."""
    try:
        from core import build_watchdog as _wd
        snap = await _wd.health_snapshot()
    except Exception as e:
        snap = {"ok": False, "error": str(e)}
    try:
        snap["active_runners"] = list(_active_runners)[:50]
        snap["in_memory_builds"] = len(_builds)
    except Exception:
        pass
    return snap


@router.get("/diagnose/{build_id}")
async def diagnose_build(build_id: str) -> dict:
    """Deep diagnostics for a single build: runner status, last heartbeat,
    batch log summary, Mongo presence, cold-storage state."""
    try:
        from services.database import db as _db
    except Exception:
        _db = None

    build = await load_build(build_id)
    if not build:
        mongo_present = False
        if _db is not None:
            try:
                mongo_present = bool(await _db.galaxy_builds.find_one(
                    {"build_id": build_id}, {"build_id": 1}))
            except Exception:
                pass
        return {
            "ok": False, "build_id": build_id, "reason": "not_found",
            "in_memory": False, "in_mongo": mongo_present,
            "active_runner": build_id in _active_runners,
        }
    phase_log = build.get("_bg_phase_log", []) or []
    recent = phase_log[-5:] if phase_log else []
    return {
        "ok": True,
        "build_id": build_id,
        "title": build.get("title"),
        "genre": build.get("genre"),
        "status": build.get("status"),
        "bg_status": build.get("_bg_status"),
        "current_phase": build.get("current_phase"),
        "total_phases": build.get("total_phases"),
        "file_count": build.get("file_count", 0),
        "current_batch": build.get("_bg_current_batch"),
        "total_batches": TOTAL_BATCHES,
        "parallel_workers": build.get("_bg_workers"),
        "last_heartbeat": build.get("_bg_last_heartbeat"),
        "started_at": build.get("_bg_started"),
        "completed_at": build.get("_bg_completed"),
        "errors_count": len(build.get("_bg_errors", []) or []),
        "recent_phases": recent,
        "active_runner": build_id in _active_runners,
        "in_memory": build_id in _builds,
    }


@router.post("/force-advance/{build_id}")
async def force_advance(build_id: str, batches: int = 1) -> dict:
    """Emergency lever — manually advance a build by N batches. Useful when
    a specific batch phase is stuck and the user wants to push past it.
    Runs synchronously up to ``batches`` times (capped at 10)."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build.get("status") == "completed":
        return {"ok": True, "status": "completed", "message": "nothing to advance"}
    advanced = 0
    for _ in range(max(1, min(int(batches), 10))):
        try:
            await advance_build(build_id)
            advanced += 1
        except Exception as e:
            return {"ok": False, "advanced": advanced, "error": str(e)[:200]}
    await save_build(build)
    return {
        "ok": True, "build_id": build_id, "advanced": advanced,
        "current_phase": build.get("current_phase"),
        "file_count": build.get("file_count", 0),
    }


__all__ = ["router"]
