"""Apply optical mass bias to physics."""
from __future__ import annotations
from typing import Dict, Any

def bias_mass(mass: float, optical: float) -> Dict[str, Any]:
    if mass <= 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "biased": mass}
    biased = mass * (0.8 + optical * 0.4)
    return {"ok": True, "mass": mass, "biased": biased, "optical": optical, "reason": "ok"}
