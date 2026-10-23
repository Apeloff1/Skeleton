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

from fastapi import APIRouter, HTTPException, Query

from routes.galaxy_studio_state import (
    _builds,
    _active_runners,
    TOTAL_BATCHES,
    load_build,
    save_build,
    advance_build,
)

router = APIRouter(tags=["galaxy-studio"])


@router.post("/resurrect/{build_id}")
async def resurrect_build(build_id: str, duration_minutes: int = Query(default=15, ge=1, le=60)) -> dict:
    """Explicit orphan recovery through the canonical admission owner."""
    from core.build_watchdog import _restart_runner
    from routes.galaxy_studio import _build_has_live_work

    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found — cannot resume")
    if _build_has_live_work(build_id):
        return {
            "ok": True,
            "build_id": build_id,
            "status": build.get("_bg_status", "running"),
            "message": "runner or physical work remains active",
        }
    if build.get("status") in {"completed", "failed", "cancelled", "aborted"} or build.get(
        "_bg_stop_requested"
    ):
        return {
            "ok": True,
            "build_id": build_id,
            "status": build.get("status"),
            "stop_reason": build.get("_bg_stop_reason"),
            "message": "terminal builds require an explicit start",
        }
    # Existing persisted budget is authoritative; recovery cannot renew it
    # by supplying a longer duration on every request.
    budget = build.get("_bg_target_duration", duration_minutes)
    started = await _restart_runner(build_id, budget)
    return {
        "ok": started,
        "build_id": build_id,
        "status": "resurrected" if started else build.get("_bg_status", build.get("status")),
        "stop_reason": build.get("_bg_stop_reason"),
        "total_batches": TOTAL_BATCHES,
        "message": (
            "resumed under retained worker custody"
            if started
            else "not admitted; inspect status or wait for the active build"
        ),
    }


@router.get("/watchdog/health")
async def watchdog_health() -> dict:
    """Diagnostic endpoint — returns watchdog scan counts, interval,
    and a snapshot of active-builds + runner sets."""
    try:
        from core import build_watchdog as _wd

        snap = await _wd.health_snapshot()
    except Exception:
        snap = {"ok": False, "error": "watchdog_health_unavailable"}
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
                mongo_present = bool(
                    await _db.galaxy_builds.find_one({"build_id": build_id}, {"build_id": 1})
                )
            except Exception:
                pass
        return {
            "ok": False,
            "build_id": build_id,
            "reason": "not_found",
            "in_memory": False,
            "in_mongo": mongo_present,
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
    """Generate up to N actual durable batches under canonical admission.
    This endpoint cannot skip a failed phase or overlap a running worker.
    """
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
        except HTTPException:
            raise
        except Exception:
            return {"ok": False, "advanced": advanced, "error": "force_advance_failed"}
    await save_build(build)
    return {
        "ok": True,
        "build_id": build_id,
        "advanced": advanced,
        "current_phase": build.get("current_phase"),
        "file_count": build.get("file_count", 0),
    }


__all__ = ["router"]
