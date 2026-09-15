"""
core/boot_timeline.py — ring-buffer of structured boot events.

High-volume but bounded: 2000 events max, oldest evicted first. Every
event is { ts, type, data… }. Consumers:

  * /api/health/boot/timeline — paginated read
  * frontend BootLauncher — polls for live progress
  * SRE dashboards — LOG_FORMAT=json mirrors these into stdout

Designed to never block: append is O(1), no I/O, no locks.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

MAX_EVENTS = 2000
_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_boot_at: float = time.time()


def emit(event_type: str, **data: Any) -> None:
    """Append a single event. Never raises."""
    try:
        _events.append({
            "ts": time.time(),
            "t_rel": round(time.time() - _boot_at, 4),
            "type": event_type,
            **data,
        })
    except Exception:
        pass  # best-effort — telemetry is non-critical


def recent(limit: int = 200, after_ts: float | None = None) -> list[dict[str, Any]]:
    items = list(_events)
    if after_ts is not None:
        items = [e for e in items if e["ts"] > after_ts]
    return items[-max(1, min(limit, MAX_EVENTS)):]


def stats() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for e in _events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return {
        "total": len(_events),
        "capacity": MAX_EVENTS,
        "counts": counts,
        "boot_at": _boot_at,
        "uptime_s": round(time.time() - _boot_at, 2),
    }


def clear() -> None:
    _events.clear()
