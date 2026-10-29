"""All-in fidelity high-water lock."""
from __future__ import annotations
from typing import Dict, Any

def ratchet_allin(current: float, previous: float) -> Dict[str, Any]:
    if current < 0.92:
        return {"ok": False, "reason": "below_floor", "locked": False}
    high = max(current, previous)
    return {"ok": True, "high": high, "current": current, "locked": True, "reason": "ok"}
