"""VFX effect 0022.
"""
from __future__ import annotations

VFX = "vfx_0022"

def spawn(origin: str, intensity: float = 0.8) -> dict:
    if not origin:
        return {"ok": False, "reason": "no_origin"}
    return {"ok": True, "vfx": VFX, "origin": origin, "intensity": round(max(0.0, min(1.0, intensity)), 3)}

def lifetime() -> float:
    return round(0.5 + (22 % 10) * 0.15, 2)
