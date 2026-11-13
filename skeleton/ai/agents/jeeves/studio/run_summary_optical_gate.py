"""Optical gate for run summary."""
from __future__ import annotations
from typing import Dict, Any

def gate_summary(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "pct": 0.0}
    pct = min(100.0, rooms * optical * 8)
    return {"ok": True, "pct": pct, "optical": optical, "reason": "ok"}
