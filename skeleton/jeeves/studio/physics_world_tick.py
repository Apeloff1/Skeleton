"""Tick physics world with optical."""
from __future__ import annotations
from typing import Dict, Any

def tick_world(bodies: int, dt: float, optical: float) -> Dict[str, Any]:
    if bodies < 1 or dt <= 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "ticked": False}
    return {"ok": True, "bodies": bodies, "dt": dt, "optical": optical, "ticked": True, "reason": "ok"}
