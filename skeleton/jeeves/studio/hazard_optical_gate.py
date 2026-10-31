"""Optical gate for hazards."""
from __future__ import annotations
from typing import Dict, Any

def gate_hazard(optical: float) -> Dict[str, Any]:
    if optical < 0.7:
        return {"ok": False, "reason": "floors", "intensity": 1.0}
    intensity = 1.2 - optical * 0.3
    return {"ok": True, "intensity": intensity, "optical": optical, "reason": "ok"}
