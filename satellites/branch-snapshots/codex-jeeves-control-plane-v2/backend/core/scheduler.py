"""
core/scheduler.py — Stage E1 background task runner (APScheduler, async).

A single process-wide AsyncIOScheduler that runs the fabric's autonomic upkeep:

  * ``lafs_online_sweep``  — periodic self-learning sweep (compounds the brain).
  * ``legion_drill``       — small periodic legion wave so competency keeps
                             rising even when no user is present ("training").
  * ``fabric_snapshot``    — force-persist the Ω-fabric + delta memory.

Intervals are read from settings (with safe defaults) and every job is wrapped
so a failure is logged to the PROOD event bus but never crashes the loop.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

_scheduler = None          # AsyncIOScheduler singleton
_last_runs: Dict[str, dict] = {}


async def _safe(job_name: str, coro):
    t0 = time.time()
    try:
        result = await coro
        _last_runs[job_name] = {"ok": True, "ts": time.time(),
                                "ms": round((time.time() - t0) * 1000, 1),
                                "result": result}
    except Exception as e:  # noqa: BLE001
        _last_runs[job_name] = {"ok": False, "ts": time.time(), "error": str(e)[:200]}
        try:
            from gameforge.prood import event_bus
            await event_bus.publish("scheduler.job.fail", {"job": job_name, "error": str(e)[:120]})
        except Exception:  # noqa: BLE001
            pass


# ── jobs ───────────────────────────────────────────────────────
async def lafs_online_sweep():
    from routes.lafs import sweep_online
    return await _safe("lafs_online_sweep", sweep_online(count=3))


async def legion_drill():
    async def _drill():
        from gameforge.omega import legion_command
        # rotate a light training wave across the whole army
        return await legion_command.jeeves_mobilize_all(wave_size=120, directive="autonomic drill")
    return await _safe("legion_drill", _drill())


async def fabric_snapshot():
    async def _snap():
        from gameforge.omega.integration import omega_fabric
        await omega_fabric._persist_state(force=True)
        return {"persisted": True}
    return await _safe("fabric_snapshot", _snap())


async def idle_augment():
    """If Jeeves has been idle > 4h, SPEND the whole free-tier budget augmenting
    his knowledge — run online-learning sweeps whose accepted sheets queue for
    jury review (compounding the wiki while nobody is watching)."""
    async def _aug():
        from gameforge.jeeves.free_tier import free_tier
        if not free_tier.should_augment_idle():
            return {"augmented": False, "idle_seconds": round(free_tier.idle_seconds(), 1)}
        from routes.lafs import sweep_online
        learned = 0
        # spend free units in batches until the window budget is exhausted
        while free_tier.free_remaining() > 0:
            free_tier.free_used += 4
            res = await sweep_online(count=4)
            learned += res.get("learned_count", 0)
            # queue newly learned sheets for jury review
            try:
                from gameforge.lafs import lafs
                for r in res.get("results", []):
                    if r.get("sheet_id"):
                        lafs.queue_for_jury(r["sheet_id"], reason="idle_augment")
            except Exception:  # noqa: BLE001
                pass
            if learned > 40:
                break
        free_tier.idle_augmentations += 1
        free_tier.touch()  # reset idle after augmenting
        return {"augmented": True, "sheets_learned": learned}
    return await _safe("idle_augment", _aug())


# ── lifecycle ──────────────────────────────────────────────────
def start_scheduler() -> bool:
    global _scheduler
    if _scheduler is not None:
        return False
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception:  # noqa: BLE001
        return False
    sch = AsyncIOScheduler(timezone="UTC")
    # sane defaults; short enough to be demonstrable, long enough to be cheap
    sch.add_job(lafs_online_sweep, "interval", minutes=30, id="lafs_online_sweep",
                max_instances=1, coalesce=True)
    sch.add_job(legion_drill, "interval", minutes=10, id="legion_drill",
                max_instances=1, coalesce=True)
    sch.add_job(fabric_snapshot, "interval", minutes=5, id="fabric_snapshot",
                max_instances=1, coalesce=True)
    sch.add_job(idle_augment, "interval", minutes=15, id="idle_augment",
                max_instances=1, coalesce=True)
    try:
        sch.start()
    except Exception:  # noqa: BLE001
        return False
    _scheduler = sch
    return True


def scheduler_status() -> Dict:
    if _scheduler is None:
        return {"running": False, "jobs": [], "last_runs": _last_runs}
    jobs = [{"id": j.id, "next_run": str(j.next_run_time)} for j in _scheduler.get_jobs()]
    return {"running": True, "jobs": jobs, "last_runs": _last_runs}


async def run_job_now(job_id: str) -> Dict:
    """Manually trigger a scheduled job (for demos / ops)."""
    mapping = {"lafs_online_sweep": lafs_online_sweep,
               "legion_drill": legion_drill,
               "fabric_snapshot": fabric_snapshot,
               "idle_augment": idle_augment}
    fn = mapping.get(job_id)
    if not fn:
        return {"ok": False, "error": "unknown_job"}
    await fn()
    return {"ok": True, "job": job_id, "last_run": _last_runs.get(job_id)}


__all__ = ["start_scheduler", "scheduler_status", "run_job_now"]
