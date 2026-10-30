"""Physics scale 0139.
"""
from __future__ import annotations

PHYS = "phys_scale_0139"

def integrate(vel: float, accel: float, dt: float = 0.016) -> dict:
    return {"ok": True, "phys": PHYS, "vel": round(vel + accel * dt, 3), "dt": dt}

def collide(a: float, b: float) -> dict:
    return {"ok": True, "phys": PHYS, "overlap": abs(a - b) < 0.5}
