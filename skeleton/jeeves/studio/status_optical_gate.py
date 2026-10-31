"""Optical gate for status effects."""
from __future__ import annotations
from typing import Dict, Any

def gate_status(duration: int, optical: float) -> Dict[str, Any]:
    if duration < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "ticks": 0}
    ticks = int(duration * optical)
    return {"ok": True, "ticks": ticks, "optical": optical, "reason": "ok"}
