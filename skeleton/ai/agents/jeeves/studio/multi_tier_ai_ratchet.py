"""Multi-tier AI ratchet locks high-water fidelity."""
from __future__ import annotations
from typing import Dict, Any

def ratchet_lock(current: float, high_water: float) -> Dict[str, Any]:
    if current < 0.92:
        return {"ok": False, "reason": "below_floor", "locked": False}
    locked = current >= high_water
    return {"ok": True, "current": current, "high_water": max(current, high_water), "locked": locked, "reason": "ok"}
