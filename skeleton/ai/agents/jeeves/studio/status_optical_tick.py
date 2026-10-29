"""Tick status effects with optical."""
from __future__ import annotations
from typing import Dict, Any

def tick_status(duration: int, optical: float) -> Dict[str, Any]:
    if duration < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "remaining": 0}
    remaining = max(0, duration - 1)
    return {"ok": True, "remaining": remaining, "optical": optical, "reason": "ok"}
