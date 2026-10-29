"""Tech 0003.
"""
from __future__ import annotations

TECH = "tech_0003"

def progress(points: int, cost: int = 100) -> dict:
    return {"ok": True, "tech": TECH, "done": points >= cost, "points": points, "cost": cost}
