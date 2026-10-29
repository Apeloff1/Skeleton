"""Physics 0074.
"""
from __future__ import annotations

PHYS = "phys_0074"

def integrate(vel: float, accel: float, dt: float = 0.016) -> dict:
    new_vel = vel + accel * dt
    return {"ok": True, "phys": PHYS, "vel": round(new_vel, 3), "dt": dt}

def collide(a: float, b: float) -> dict:
    return {"ok": True, "phys": PHYS, "overlap": abs(a - b) < 0.5}
