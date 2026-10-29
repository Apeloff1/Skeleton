"""Optical gate for progress."""
from __future__ import annotations
from typing import Dict, Any

def gate_progress(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "percent": 0.0}
    percent = min(100.0, rooms * optical * 10)
    return {"ok": True, "percent": percent, "rooms": rooms, "optical": optical, "reason": "ok"}
