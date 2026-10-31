"""Projectile 0073.
"""
from __future__ import annotations

PROJ = "proj_0073"

def fire(origin: str, speed: float = 12.0) -> dict:
    if not origin:
        return {"ok": False, "reason": "no_origin"}
    return {"ok": True, "proj": PROJ, "origin": origin, "speed": speed, "damage": 8 + (73 % 10)}
