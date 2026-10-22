"""
╔════════════════════════════════════════════════════════════════════════╗
║  BUILD WATCHDOG — self-healing layer for active Galaxy Studio builds   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Runs a periodic background task that:                                 ║
║    • Discovers all builds with status == 'building'                    ║
║    • Restarts any that have no active runner (orphan recovery)         ║
║    • Stops overdue builds while retaining physical worker custody            ║
║    • Snapshots build metadata to compressed vault every N seconds so   ║
║      a node crash never loses the build                                ║
║                                                                        ║
║  This layer is idempotent and race-safe — every step uses the          ║
║  existing galaxy_studio helpers (_save_build, _load_build,              ║
║  _active_runners, _run_background_build).                              ║
╚════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("GalaxyStudio.Watchdog")

# Tuning
CHECK_INTERVAL_SEC = 20  # how often the watchdog tick runs
STALE_AFTER_SEC = 90  # diagnostic only; heartbeat age is not worker death
SNAPSHOT_EVERY_SEC = 60  # flush build snapshot to vault this often
FORCE_COMPLETE_AT = 1.0  # compatibility name: deadline requests a truthful stop

# ─── Orphan-recovery rate limits (2026-02-18) ───────────────────────────
# Without these, a watchdog activation on a host with many orphan builds
# would resurrect them ALL on the first tick, saturating CPU/memory.
WARMUP_TICKS = 3  # first N ticks: no orphan restarts
MAX_RESTARTS_PER_TICK = 1  # cap restarts per single sweep
MAX_RESTARTS_PER_5MIN = 3  # rolling window cap

_watchdog_task: asyncio.Task | None = None
_stopped = False
_tick_count: int = 0
_restart_history: list[float] = []  # epoch seconds of recent restarts
_last_tick_at: float = 0.0
_last_counts: dict[str, int] = {}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _snapshot_to_vault(build: dict) -> bool:
    """Persist build metadata to Mongo via the robust `_save_build` path
    (which already handles BSON-size overflow via minimal-save fallback).
    This doubles as our crash-recovery snapshot."""
    try:
        from routes.galaxy_studio import _save_build

        return await _save_build(build) is True
    except Exception as e:
        logger.debug("snapshot skipped: %s", type(e).__name__)
        return False


async def _restart_runner(build_id: str, duration_min: int) -> bool:
    """Resume an actual orphan, retaining the same task handle as admission."""
    from routes.galaxy_studio import (
        TOTAL_BATCHES,
        _run_background_build,
        _active_runners,
        _load_build,
        _background_tasks,
        _any_build_has_live_work,
        _request_build_stop,
        _active_artifact_job,
    )

    if type(duration_min) is not int or not 1 <= duration_min <= 60:
        return False
    build = await _load_build(build_id)
    if (
        not build
        or build.get("status") != "building"
        or build.get("_bg_stop_requested")
        or _active_artifact_job(build) is not None
    ):
        return False
    elapsed = _age_seconds(build.get("_bg_started"))
    if elapsed is None or elapsed < -5:
        await _request_build_stop(build_id, "build_clock_unavailable", failed=True)
        return False
    if elapsed >= duration_min * 60:
        await _request_build_stop(build_id, "build_deadline_exceeded", failed=True)
        return False
    # Recheck after the load await. Never replace a live task, native future,
    # or reserved single-builder slot because its heartbeat is old.
    if _any_build_has_live_work():
        return False
    try:
        completed = build.get("_bg_last_batch_completed")
        resume_from = (
            max(1, int(completed) + 1)
            if completed is not None
            else max(1, int(build.get("_bg_current_batch", 1)))
        )
        if resume_from > TOTAL_BATCHES + 1:
            return False
        _active_runners.add(build_id)
        task = asyncio.create_task(
            _run_background_build(build_id, duration_min, resume_from_batch=resume_from)
        )
        _background_tasks[build_id] = task
        logger.info("[watchdog] resumed build %s from batch %s", build_id, resume_from)
        return True
    except Exception as exc:
        _active_runners.discard(build_id)  # no task was admitted
        logger.warning("[watchdog] restart failed for %s: %s", build_id, type(exc).__name__)
        return False


async def _force_complete(build_id: str) -> None:
    """Compatibility helper: deadlines stop work; they never complete phases."""
    from routes.galaxy_studio import _request_build_stop

    await _request_build_stop(build_id, "build_deadline_exceeded", failed=True)
    logger.warning("[watchdog] requested deadline stop for %s; partial artifacts retained", build_id)


def _age_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - stamp).total_seconds()
    except (ValueError, TypeError):
        return None


async def _scan_once() -> dict:
    """One bounded sweep. Timed-out work increments stopped, never completed."""
    global _tick_count, _restart_history
    _tick_count += 1
    counts = {
        "restarted": 0,
        "completed": 0,
        "stopped": 0,
        "stale_live": 0,
        "snapshotted": 0,
        "scanned": 0,
        "skipped_warmup": 0,
        "skipped_ratelimit": 0,
    }
    # Drop restart-history entries older than 5 minutes
    cutoff = time.time() - 300
    _restart_history = [t for t in _restart_history if t > cutoff]
    restarts_this_tick = 0

    try:
        from routes.galaxy_studio import (
            _builds,
            _load_build,
            _build_has_live_work,
            _request_build_stop,
            _active_artifact_job,
        )
        from services.database import db as _db

        # Collect ids from both in-memory and Mongo
        seen_ids: set[str] = set(_builds.keys())
        try:
            cursor = _db.galaxy_builds.find(
                {"status": "building"},
                {"build_id": 1, "_id": 0},
                limit=200,
            )
            async for doc in cursor:
                bid = doc.get("build_id")
                if bid:
                    seen_ids.add(bid)
        except Exception as e:
            logger.debug(f"[watchdog] mongo scan failed: {e}")

        now = time.time()
        for bid in list(seen_ids):
            counts["scanned"] += 1
            try:
                b = _builds.get(bid) or await _load_build(bid)
                if not b:
                    continue
                if (
                    b.get("status") != "building"
                    or b.get("_bg_status") == "manual"
                    or _active_artifact_job(b) is not None
                ):
                    continue

                target_min = b.get("_bg_target_duration", 15)
                if type(target_min) is not int or not 1 <= target_min <= 60:
                    await _request_build_stop(bid, "build_duration_invalid", failed=True)
                    counts["stopped"] += 1
                    continue
                elapsed_sec = _age_seconds(b.get("_bg_started"))
                if b.get("_bg_stop_requested"):
                    await _request_build_stop(bid, str(b.get("_bg_stop_reason") or "build_stopped"))
                    continue
                if elapsed_sec is None or elapsed_sec < -5:
                    await _request_build_stop(bid, "build_clock_unavailable", failed=True)
                    counts["stopped"] += 1
                    continue
                if elapsed_sec > target_min * 60 * FORCE_COMPLETE_AT:
                    await _force_complete(bid)
                    counts["stopped"] += 1
                    continue
                live = _build_has_live_work(bid)
                heartbeat_age = _age_seconds(b.get("_bg_last_heartbeat"))
                if live and heartbeat_age is not None and heartbeat_age > STALE_AFTER_SEC:
                    counts["stale_live"] += 1
                    # Staleness is evidence for diagnostics, never evidence
                    # that a physical executor has released its slot.

                # (b2) Orphan detection — status=building but no active runner.
                # RATE LIMITS (2026-02-18):
                #   • First WARMUP_TICKS sweeps after boot: skip restarts so
                #     a stale orphan list can be diagnosed / cleaned manually.
                #   • Per tick: at most MAX_RESTARTS_PER_TICK new runners.
                #   • Per 5-min rolling window: at most MAX_RESTARTS_PER_5MIN.
                if not live:
                    if _tick_count <= WARMUP_TICKS:
                        counts["skipped_warmup"] += 1
                        continue
                    if restarts_this_tick >= MAX_RESTARTS_PER_TICK:
                        counts["skipped_ratelimit"] += 1
                        continue
                    if len(_restart_history) >= MAX_RESTARTS_PER_5MIN:
                        counts["skipped_ratelimit"] += 1
                        continue
                    ok = await _restart_runner(bid, int(target_min))
                    if ok:
                        counts["restarted"] += 1
                        restarts_this_tick += 1
                        _restart_history.append(now)

                # (c) Periodic snapshot
                last_snap = float(b.get("_watchdog_last_snap", 0) or 0)
                if now - last_snap >= SNAPSHOT_EVERY_SEC:
                    if await _snapshot_to_vault(b):
                        b["_watchdog_last_snap"] = now
                        counts["snapshotted"] += 1
            except Exception as e:
                logger.debug(f"[watchdog] per-build check failed for {bid}: {e}")
    except Exception as e:
        logger.warning(f"[watchdog] scan failure: {e}")
    return counts


async def _loop():
    logger.info(
        f"[watchdog] started (interval={CHECK_INTERVAL_SEC}s, "
        f"warmup={WARMUP_TICKS} ticks, "
        f"max_restarts/tick={MAX_RESTARTS_PER_TICK}, "
        f"max_restarts/5min={MAX_RESTARTS_PER_5MIN})"
    )
    while not _stopped:
        try:
            counts = await _scan_once()
            # Update last-tick timestamp so LoadSheddingMiddleware can detect
            # a stale watchdog and shed load when the loop is wedged.
            globals()["_last_tick_at"] = time.time()
            globals()["_last_counts"] = dict(counts)
            # Log only ticks with action, but always log warmup ticks for
            # diagnostics, and rate-limited skips so they're visible.
            if (
                counts["restarted"]
                or counts["stopped"]
                or counts["skipped_warmup"]
                or counts["skipped_ratelimit"]
                or _tick_count <= WARMUP_TICKS
            ):
                logger.info(f"[watchdog] tick {_tick_count}: {counts}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[watchdog] loop error: {e}")
        try:
            await asyncio.sleep(CHECK_INTERVAL_SEC)
        except asyncio.CancelledError:
            break


def start_watchdog() -> None:
    global _watchdog_task, _stopped
    if _watchdog_task is not None and not _watchdog_task.done():
        return
    _stopped = False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    _watchdog_task = loop.create_task(_loop())


def stop_watchdog() -> None:
    global _stopped
    _stopped = True
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()


async def health_snapshot() -> dict:
    """Read-only inspection; health polling cannot restart or stop builds."""
    running = bool(_watchdog_task is not None and not _watchdog_task.done() and not _stopped)
    return {
        "ok": running,
        "running": running,
        "counts": dict(_last_counts),
        "last_tick_at": _last_tick_at or None,
        "interval_sec": CHECK_INTERVAL_SEC,
        "snapshot_every_sec": SNAPSHOT_EVERY_SEC,
        "force_complete_multiplier": None,  # legacy field: force-completion is disabled
        "deadline_stop_multiplier": FORCE_COMPLETE_AT,
    }
