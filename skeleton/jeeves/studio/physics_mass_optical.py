"""Optical mass for physics bodies."""
from __future__ import annotations
from typing import Dict, Any

def apply_optical_mass(body: Dict[str, Any], optical: float) -> Dict[str, Any]:
    if not isinstance(body, dict) or optical < 0.6:
        return {"ok": False, "reason": "bad_input", "mass": 1.0}
    mass = body.get("mass", 1.0) * (0.8 + optical * 0.4)
    return {"ok": True, "mass": round(mass, 2), "optical": optical, "reason": "ok"}
