"""
routes/expo_flaps.py — exposes the expo_smart_start.sh flap log so the
frontend tunnel-status pill / SRE dashboard can see *why* the tunnel
restarted.

GET /api/health/expo-flaps?limit=N
    Returns the last N events from /var/log/supervisor/expo_flaps.log
    in chronological order. Each row is TAB-separated:
        ts<TAB>kind<TAB>detail

Rolls up:
  * count last 10 minutes
  * count last 60 minutes
  * most recent ngrok_cooloff timestamp (helps debug ngrok-specific issues)
"""
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(tags=["ExpoFlaps"], prefix="/health")

FLAP_LOG_PATH = os.environ.get("EXPO_FLAP_LOG", "/var/log/supervisor/expo_flaps.log")


def _read_events(limit: int) -> list[dict[str, Any]]:
    try:
        # Cheap tail: read up to ~256 KB from the end.
        size = os.path.getsize(FLAP_LOG_PATH)
        with open(FLAP_LOG_PATH, "rb") as f:
            chunk = 256 * 1024
            f.seek(max(0, size - chunk))
            raw = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in raw.splitlines() if "\t" in ln]
        rows: list[dict[str, Any]] = []
        for ln in lines[-limit:]:
            parts = ln.split("\t", 2)
            if len(parts) >= 2:
                try: ts = float(parts[0])
                except ValueError: continue
                rows.append({"ts": ts, "kind": parts[1], "detail": parts[2] if len(parts) > 2 else ""})
        return rows
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        return [{"ts": time.time(), "kind": "error", "detail": f"{type(e).__name__}: {e}"}]


@router.get("/expo-flaps")
async def get_expo_flaps(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    rows = _read_events(limit)
    now = time.time()
    last_10m = sum(1 for r in rows if (now - r["ts"]) < 600 and r["kind"] == "exit")
    last_60m = sum(1 for r in rows if (now - r["ts"]) < 3600 and r["kind"] == "exit")
    last_ngrok_cooloff = max(
        (r["ts"] for r in rows if r["kind"] == "ngrok_cooloff"),
        default=None,
    )
    last_giveup = max(
        (r["ts"] for r in rows if r["kind"] == "giveup"),
        default=None,
    )
    return {
        "ok": True,
        "log_path": FLAP_LOG_PATH,
        "rolling": {
            "exits_last_10m": last_10m,
            "exits_last_60m": last_60m,
            "last_ngrok_cooloff_ts": last_ngrok_cooloff,
            "last_giveup_ts": last_giveup,
        },
        "events": rows,
    }
