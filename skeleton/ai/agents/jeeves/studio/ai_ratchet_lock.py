"""Lock AI ratchet at high-water."""
from __future__ import annotations
from typing import Dict, Any

def lock_ratchet(current: float, high: float) -> Dict[str, Any]:
    if current < 0.92:
        return {"ok": False, "reason": "below_floor", "locked": False}
    locked_high = max(current, high)
    return {"ok": True, "current": current, "high": locked_high, "locked": True, "reason": "ok"}
