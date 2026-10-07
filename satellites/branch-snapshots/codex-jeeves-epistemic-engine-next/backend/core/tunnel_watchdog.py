"""
core/tunnel_watchdog.py — passive proxy-outage detector (Feb 2026).

We can't fix ngrok flaps in the preview environment, but we CAN measure
them and surface them to the frontend so the user understands why the
app briefly stops responding.

Mechanics:
  * Every successful request bumps ``last_seen_ts`` from the request
    middleware (best-effort, never blocks).
  * A 5-second background loop records the gap between *now* and
    ``last_seen_ts``. If it exceeds the configured threshold we mark
    the tunnel "degraded".
  * /api/health/tunnel returns the rolling histogram so the frontend's
    TunnelStatusPill can render reliably.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

_state: dict[str, Any] = {
    "last_seen_ts": time.time(),
    "flap_count": 0,            # rolling 5-minute count of degraded → ok transitions
    "status": "ok",             # "ok" | "degraded" | "down"
    "gap_history": deque(maxlen=120),     # last 10 minutes @ 5s ticks
    "started_at": time.time(),
    "task": None,               # asyncio.Task | None
}

DEGRADED_AFTER_S = 15.0   # no traffic for 15s → degraded
DOWN_AFTER_S = 60.0       # no traffic for 60s → down
TICK_INTERVAL_S = 5.0


def mark_seen() -> None:
    """O(1) — called from request middleware on every 2xx."""
    _state["last_seen_ts"] = time.time()


def _classify(gap_s: float) -> str:
    if gap_s >= DOWN_AFTER_S:     return "down"
    if gap_s >= DEGRADED_AFTER_S: return "degraded"
    return "ok"


async def _loop() -> None:
    prev = "ok"
    while True:
        try:
            await asyncio.sleep(TICK_INTERVAL_S)
            gap = time.time() - _state["last_seen_ts"]
            cur = _classify(gap)
            _state["gap_history"].append({"ts": time.time(), "gap": round(gap, 2), "status": cur})
            _state["status"] = cur
            if prev != "ok" and cur == "ok":
                _state["flap_count"] = int(_state["flap_count"]) + 1
            prev = cur
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            print(f"[tunnel_watchdog] loop error: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(5)


async def start() -> None:
    """Idempotent — starts the background tick loop once."""
    t: asyncio.Task | None = _state.get("task")
    if t and not t.done(): return
    _state["task"] = asyncio.create_task(_loop())


async def stop() -> None:
    t: asyncio.Task | None = _state.get("task")
    if t and not t.done():
        t.cancel()
        try: await t
        except Exception: pass
    _state["task"] = None


def snapshot() -> dict[str, Any]:
    gap = time.time() - _state["last_seen_ts"]
    return {
        "ok": _state["status"] == "ok",
        "status": _state["status"],
        "gap_since_last_request_s": round(gap, 2),
        "degraded_after_s": DEGRADED_AFTER_S,
        "down_after_s": DOWN_AFTER_S,
        "flap_count_total": int(_state["flap_count"]),
        "uptime_s": round(time.time() - _state["started_at"], 1),
        "tick_interval_s": TICK_INTERVAL_S,
        "history_size": len(_state["gap_history"]),
        "recent": list(_state["gap_history"])[-20:],   # last 100 s of ticks
    }
