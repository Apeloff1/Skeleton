"""
core/feature_flags_metrics.py — Prometheus + impression analytics.

Tracks:
  * `feature_flag_resolved_total{name, env, value}` — every time a server
    resolves a flag we bump the counter. Cheap O(1) in-process; exposed
    via the existing /api/metrics endpoint.
  * impressions ingest — clients POST batched impressions to
    /api/feature-flags/impressions; we aggregate in-memory and flush to
    `feature_flag_impressions` collection on a 60-second timer.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from core.databases import core_db

COLLECTION = "feature_flag_impressions"
FLUSH_INTERVAL_S = 60.0

# (name, env, value) -> count, since boot
_counter: dict[tuple[str, str, str], int] = defaultdict(int)

# (name, value, day_bucket) -> count, since last flush
_pending: dict[tuple[str, str, str], int] = defaultdict(int)
# Lazy-init Lock to avoid event-loop binding crashes in production K8s.
_pending_lock: asyncio.Lock | None = None

def _get_pending_lock() -> asyncio.Lock:
    global _pending_lock
    if _pending_lock is None:
        _pending_lock = asyncio.Lock()
    return _pending_lock
_flusher_task: asyncio.Task | None = None


def inc_resolved(name: str, env: str, value: bool) -> None:
    """Bump the Prometheus counter for a single resolution (sync-safe)."""
    _counter[(name, env, "true" if value else "false")] += 1


async def add_impression_batch(rows: list[dict[str, Any]]) -> int:
    """Accept a client-side batch of {name, value, ts} impressions."""
    if not rows:
        return 0
    added = 0
    async with _get_pending_lock():
        day = time.strftime("%Y-%m-%d")
        for r in rows[:500]:    # hard cap to prevent OOM if a client misbehaves
            try:
                name = str(r.get("name"))
                val  = "true" if r.get("value") else "false"
                if not name:
                    continue
                _pending[(name, val, day)] += int(r.get("count", 1)) or 1
                added += 1
            except Exception:
                continue
    return added


def prom_lines() -> list[str]:
    """Format the in-process counter as Prom text exposition lines."""
    out = [
        "# HELP feature_flag_resolved_total Server-side flag resolutions since boot.",
        "# TYPE feature_flag_resolved_total counter",
    ]
    for (name, env, val), n in _counter.items():
        # Escape per Prom spec — backslashes + double-quotes + newlines.
        nn = name.replace('\\', '\\\\').replace('"', '\\"')
        out.append(f'feature_flag_resolved_total{{name="{nn}",env="{env}",value="{val}"}} {n}')
    return out


async def _flush_pending() -> int:
    if not _pending:
        return 0
    async with _get_pending_lock():
        snapshot = dict(_pending)
        _pending.clear()
    if not snapshot:
        return 0
    try:
        ops = []
        for (name, val, day), n in snapshot.items():
            ops.append({
                "update_one": {
                    "filter": {"name": name, "value": val, "day": day},
                    "update": {"$inc": {"count": n}, "$set": {"updated_at": time.time()}},
                    "upsert": True,
                }
            })
        # Motor bulk_write expects pymongo ops — convert.
        from pymongo import UpdateOne
        pymongo_ops = [
            UpdateOne(op["update_one"]["filter"], op["update_one"]["update"], upsert=True)
            for op in ops
        ]
        if pymongo_ops:
            await core_db[COLLECTION].bulk_write(pymongo_ops, ordered=False)
        return len(ops)
    except Exception as e:  # noqa: BLE001
        print(f"[feature_flag_metrics] flush error: {type(e).__name__}: {e}", flush=True)
        return 0


async def start_flusher() -> None:
    """Idempotent — starts the background flusher task once."""
    global _flusher_task
    if _flusher_task and not _flusher_task.done():
        return

    async def _loop():
        while True:
            try:
                await asyncio.sleep(FLUSH_INTERVAL_S)
                await _flush_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                print(f"[feature_flag_metrics] flusher loop error: {type(e).__name__}: {e}", flush=True)
                await asyncio.sleep(5)

    _flusher_task = asyncio.create_task(_loop())


async def stats() -> dict[str, Any]:
    try:
        total = await core_db[COLLECTION].estimated_document_count()
        return {
            "ok": True,
            "in_process_counter_size": len(_counter),
            "pending_impressions": sum(_pending.values()),
            "persisted_rows": int(total),
            "flusher_alive": bool(_flusher_task and not _flusher_task.done()),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
