"""Blend lighting with optical intensity."""
from __future__ import annotations
from typing import Dict, Any

def blend_light(intensity: float, optical: float) -> Dict[str, Any]:
    if intensity < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "final": 0.0}
    final = intensity * (0.7 + optical * 0.3)
    return {"ok": True, "intensity": intensity, "final": final, "optical": optical, "reason": "ok"}
