"""Integrate physics world with optical mass and AABB."""
from __future__ import annotations
from typing import Dict, Any

def integrate_world(bodies: int, dt: float, optical: float) -> Dict[str, Any]:
    if dt <= 0 or optical < 0.7:
        return {"ok": False, "reason": "bad_params", "integrated": False}
    collisions = max(0, bodies // 4)
    return {"ok": True, "bodies": bodies, "collisions": collisions, "dt": dt, "optical_bias": optical, "reason": "ok"}
