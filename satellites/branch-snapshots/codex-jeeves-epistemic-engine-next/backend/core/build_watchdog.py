"""
╔════════════════════════════════════════════════════════════════════════╗
║  BUILD WATCHDOG — self-healing layer for active Galaxy Studio builds   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Runs a periodic background task that:                                 ║
║    • Discovers all builds with status == 'building'                    ║
║    • Restarts any that have no active runner (orphan recovery)         ║
║    • Force-completes builds stuck past their target duration            ║
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
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("GalaxyStudio.Watchdog")

# Tuning
CHECK_INTERVAL_SEC = 20        # how often the watchdog tick runs
STALE_AFTER_SEC    = 90        # no phase update for 90s → reseed runner
SNAPSHOT_EVERY_SEC = 60        # flush build snapshot to vault this often
FORCE_COMPLETE_AT  = 1.5       # × target_duration → force-complete

# ─── Orphan-recovery rate limits (2026-02-18) ───────────────────────────
# Without these, a watchdog activation on a host with many orphan builds
# would resurrect them ALL on the first tick, saturating CPU/memory.
WARMUP_TICKS                 = 3   # first N ticks: no orphan restarts
MAX_RESTARTS_PER_TICK        = 1   # cap restarts per single sweep
MAX_RESTARTS_PER_5MIN        = 3   # rolling window cap

_watchdog_task: asyncio.Task | None = None
_stopped = False
_tick_count: int = 0
_restart_history: list[float] = []  # epoch seconds of recent restarts


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _snapshot_to_vault(build: dict) -> None:
    """Persist build metadata to Mongo via the robust `_save_build` path
    (which already handles BSON-size overflow via minimal-save fallback).
    This doubles as our crash-recovery snapshot."""
    try:
        from routes.galaxy_studio import _save_build
        await _save_build(build)
    except Exception as e:
        logger.debug(f"snapshot skipped: {e}")


async def _restart_runner(build_id: str, duration_min: int) -> bool:
    """Re-kick the background runner for a build that lost its task."""
    try:
        from routes.galaxy_studio import _run_background_build, _active_runners, _load_build
        if build_id in _active_runners:
            return False  # already running
        build = await _load_build(build_id)
        if not build:
            return False
        # Resume from the next batch if we already have progress
        resume_from = max(1, int(build.get("_bg_current_batch", 0)) + 1)
        if resume_from > 10:
            return False  # already complete
        _active_runners.add(build_id)
        asyncio.create_task(_run_background_build(build_id, duration_min, resume_from_batch=resume_from))
        logger.info(f"[watchdog] resurrected build {build_id} from batch {resume_from}")
        return True
    except Exception as e:
        logger.warning(f"[watchdog] restart failed for {build_id}: {e}")
        return False


async def _force_complete(build_id: str) -> None:
    try:
        from routes.galaxy_studio import _load_build, _save_build, _active_runners
        build = await _load_build(build_id)
        if not build:
            return
        build["status"] = "completed"
        build["_bg_status"] = "completed"
        build["current_phase"] = build.get("total_phases", 100)
        build["_bg_completed_at"] = _now_iso()
        await _save_build(build)
        _active_runners.discard(build_id)
        logger.info(f"[watchdog] force-completed over-runtime build {build_id}")
        # Bound disk: prune the vault after a force-complete (protect this build).
        try:
            from core import build_vault as _bv
            _pr = _bv.prune_old_builds(keep=12, protect={build_id})
            if _pr.get("pruned"):
                logger.info(f"[watchdog] vault auto-prune: {_pr}")
        except Exception as _pe:
            logger.warning(f"[watchdog] vault auto-prune failed: {_pe}")
    except Exception as e:
        logger.warning(f"[watchdog] force-complete failed for {build_id}: {e}")


async def _scan_once() -> dict:
    """One sweep. Returns counts: {restarted, completed, snapshotted, scanned, skipped_warmup, skipped_ratelimit}."""
    global _tick_count, _restart_history
    _tick_count += 1
    counts = {
        "restarted": 0, "completed": 0, "snapshotted": 0, "scanned": 0,
        "skipped_warmup": 0, "skipped_ratelimit": 0,
    }
    # Drop restart-history entries older than 5 minutes
    cutoff = time.time() - 300
    _restart_history = [t for t in _restart_history if t > cutoff]
    restarts_this_tick = 0

    try:
        from routes.galaxy_studio import _builds, _active_runners, _load_build
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
                if b.get("status") != "building":
                    continue

                started_iso = b.get("_bg_started")
                target_min = b.get("_bg_target_duration", 15)
                elapsed_sec = 0.0
                if started_iso:
                    try:
                        elapsed_sec = (datetime.utcnow() - datetime.fromisoformat(started_iso)).total_seconds()
                    except Exception:
                        pass

                # (a) Force-complete builds that have blown past their budget
                if elapsed_sec > target_min * 60 * FORCE_COMPLETE_AT:
                    await _force_complete(bid)
                    counts["completed"] += 1
                    continue

                # (b1) Zombie-runner detection — runner is "active" but has not
                # updated its heartbeat in > STALE_AFTER_SEC. Force-discard the
                # runner ref so (b2) will spawn a fresh one next tick.
                last_hb_iso = b.get("_bg_last_heartbeat")
                if bid in _active_runners and last_hb_iso:
                    try:
                        hb_age = (datetime.utcnow() - datetime.fromisoformat(last_hb_iso)).total_seconds()
                        if hb_age > STALE_AFTER_SEC:
                            _active_runners.discard(bid)
                            logger.warning(f"[watchdog] zombie runner discarded for {bid} (heartbeat age={hb_age:.0f}s)")
                    except Exception:
                        pass

                # (b2) Orphan detection — status=building but no active runner.
                # RATE LIMITS (2026-02-18):
                #   • First WARMUP_TICKS sweeps after boot: skip restarts so
                #     a stale orphan list can be diagnosed / cleaned manually.
                #   • Per tick: at most MAX_RESTARTS_PER_TICK new runners.
                #   • Per 5-min rolling window: at most MAX_RESTARTS_PER_5MIN.
                if bid not in _active_runners:
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
                    await _snapshot_to_vault(b)
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
            # Log only ticks with action, but always log warmup ticks for
            # diagnostics, and rate-limited skips so they're visible.
            if (counts["restarted"] or counts["completed"]
                    or counts["skipped_warmup"] or counts["skipped_ratelimit"]
                    or _tick_count <= WARMUP_TICKS):
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
    counts = await _scan_once()
    return {
        "ok": True,
        "counts": counts,
        "interval_sec": CHECK_INTERVAL_SEC,
        "snapshot_every_sec": SNAPSHOT_EVERY_SEC,
        "force_complete_multiplier": FORCE_COMPLETE_AT,
    }
