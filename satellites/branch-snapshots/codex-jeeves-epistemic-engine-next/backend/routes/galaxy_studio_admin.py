"""
routes/galaxy_studio_admin.py — Admin / observability sub-router.

Extracted from routes/galaxy_studio.py (Phase-6 decomposition, Feb 2026).
Four pure-read endpoints used by the build dashboard:

  GET /workers       — worker-pool stats (queue, in-flight, health)
  GET /admin-status  — live runners, memory, vault stats, zombies
  GET /my-builds     — paginated list of *all* user builds (any status)
  GET /resumable     — list of builds eligible for /resume

Shared state (``_active_runners``, ``_background_tasks``, ``_builds``,
``_worker_*``, ``TOTAL_BATCHES``) is accessed via galaxy_studio_state.
"""
from __future__ import annotations

from fastapi import APIRouter

from routes.galaxy_studio_state import (
    TOTAL_BATCHES,
    _builds,
    _active_runners,
    get_background_tasks,
    get_worker_lock,
    get_worker_stats,
    get_worker_pool,
)

router = APIRouter(tags=["galaxy-studio"])


@router.get("/workers")
async def get_worker_status():
    """Expose worker-thread pool stats for the Galaxy Studio parallel generator.
    Useful for the frontend to show parallel-generation health on the building screen."""
    _worker_lock     = get_worker_lock()
    _worker_stats    = get_worker_stats()
    _WORKER_POOL     = get_worker_pool()
    _background_tasks = get_background_tasks()

    with _worker_lock:
        stats = dict(_worker_stats)
    try:
        pending = _WORKER_POOL._work_queue.qsize() if hasattr(_WORKER_POOL, "_work_queue") else 0
    except Exception:
        pending = 0
    stats["pending_queue"]            = int(pending)
    stats["running_builds"]           = len(_active_runners)
    stats["tracked_background_tasks"] = len(_background_tasks)
    stats["health"] = (
        "excellent" if stats.get("total_failed", 0) == 0
        else "degraded" if stats.get("total_failed", 0) < 5
        else "critical"
    )
    return stats


@router.get("/resumable")
async def list_resumable_builds():
    """List builds that are paused/interrupted and can be resumed.
    Returns in-progress builds not currently actively running."""
    try:
        from services.database import db as _db
        cursor = _db.galaxy_builds.find(
            {"status": {"$in": ["building", "paused"]}},
        ).sort("created_at", -1).limit(50)
        docs = await cursor.to_list(length=50)
        out: list[dict] = []
        for d in docs:
            d.pop("_id",        None)
            d.pop("files",      None)
            d.pop("_gen_cache", None)
            bid = d.get("build_id", "")
            is_active = bid in _active_runners
            out.append({
                "build_id":             bid,
                "title":                d.get("title",     ""),
                "genre":                d.get("genre",     ""),
                "status":               d.get("status",    "unknown"),
                "bg_status":            d.get("_bg_status", "unknown"),
                "current_batch":        d.get("_bg_current_batch", 0),
                "total_batches":        TOTAL_BATCHES,
                "file_count":           d.get("file_count", 0),
                "created_at":           d.get("created_at"),
                "is_actively_running":  is_active,
                "resumable":            not is_active,
            })
        return {"builds": out, "count": len(out)}
    except Exception as e:
        return {"builds": [], "count": 0, "error": str(e)[:200]}


@router.get("/my-builds")
async def list_my_builds(limit: int = 50, status: str = ""):
    """List ALL recent builds (completed, building, failed, lost) so the
    user can recover a build_id if the frontend lost track of it.

    Returns lightweight metadata only (no files content). Filter by status
    via ``?status=completed``. Sorted newest-first.
    """
    try:
        from services.database import db as _db
        query: dict = {}
        if status:
            query["status"] = status
        cursor = _db.galaxy_builds.find(
            query,
            {"_id": 0, "files": 0, "_gen_cache": 0, "_code_refs": 0,
             "_nv_samples": 0, "_gk_samples": 0, "_swarm_transcript": 0,
             "_swarm_discourse": 0, "phases": 0, "phase_log": 0,
             "_bg_phase_log": 0, "_bg_errors": 0},
        ).sort("created_at", -1).limit(min(limit, 200))
        docs = await cursor.to_list(length=min(limit, 200))
        out: list[dict] = []
        for d in docs:
            bid = d.get("build_id", "")
            vault_present = False
            try:
                from core import build_vault as _bv
                vault_present = _bv.get_file_count(bid) > 0
            except Exception:
                pass
            out.append({
                "build_id":       bid,
                "title":          d.get("title",          ""),
                "genre":          d.get("genre",          ""),
                "subgenre":       d.get("subgenre",       ""),
                "status":         d.get("status",         "unknown"),
                "bg_status":      d.get("_bg_status"),
                "file_count":     d.get("file_count",     0),
                "vault_present":  vault_present,
                "completed_at":   d.get("completed_at"),
                "created_at":     d.get("created_at"),
                "current_phase":  d.get("current_phase",  0),
                "total_phases":   d.get("total_phases",   100),
            })
        return {"builds": out, "count": len(out)}
    except Exception as e:
        return {"builds": [], "count": 0, "error": str(e)[:200]}


@router.get("/admin-status")
async def admin_status():
    """Admin/debug snapshot — live runners, memory, vault stats, zombies."""
    try:
        import psutil as _ps
        mem = _ps.virtual_memory()
        mem_info = {
            "percent":      mem.percent,
            "total_gb":     round(mem.total     / (1024**3), 1),
            "used_gb":      round(mem.used      / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
        }
    except Exception:
        mem_info = {"percent": None}

    _background_tasks = get_background_tasks()

    live: list[dict] = []
    for bid, tsk in list(_background_tasks.items()):
        try:
            done = tsk.done() if tsk else True
        except Exception:
            done = True
        b = _builds.get(bid) or {}
        live.append({
            "build_id":      bid,
            "done":          done,
            "status":        b.get("status"),
            "bg_status":     b.get("_bg_status"),
            "file_count":    b.get("file_count", 0),
            "current_batch": b.get("_bg_current_batch"),
        })
    zombies: list[dict] = []
    for bid, b in list(_builds.items()):
        if b.get("status") == "building" and bid not in _background_tasks:
            zombies.append({
                "build_id":   bid,
                "file_count": b.get("file_count", 0),
                "title":      b.get("title"),
            })

    try:
        from core import build_vault as _bv
        vault = _bv.global_stats()
    except Exception:
        vault = {}

    return {
        "memory":                  mem_info,
        "live_runners":            live,
        "zombie_builds":           zombies,
        "total_in_memory_builds":  len(_builds),
        "total_background_tasks": len(_background_tasks),
        "vault":                   vault,
    }
