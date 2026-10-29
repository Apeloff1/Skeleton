"""Optical gate for weather."""
from __future__ import annotations
from typing import Dict, Any

def gate_weather(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "modifier": 1.0}
    modifier = 0.8 + optical * 0.3
    return {"ok": True, "modifier": modifier, "optical": optical, "reason": "ok"}
