"""Modify weather by optical."""
from __future__ import annotations
from typing import Dict, Any

def modify_weather(optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "hazard": 1.0}
    hazard = 1.2 - optical * 0.3
    return {"ok": True, "hazard": hazard, "optical": optical, "reason": "ok"}
