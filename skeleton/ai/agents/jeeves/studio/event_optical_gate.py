"""Optical gate for events."""
from __future__ import annotations
from typing import Dict, Any

def gate_event(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "event": "none"}
    event = "boss_surge" if optical > 0.9 else "loot_rain" if optical > 0.82 else "ambient"
    return {"ok": True, "event": event, "optical": optical, "reason": "ok"}
