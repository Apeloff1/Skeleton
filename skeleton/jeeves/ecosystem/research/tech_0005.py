"""Tech 0005.
"""
from __future__ import annotations

TECH = "tech_0005"

def progress(points: int, cost: int = 100) -> dict:
    return {"ok": True, "tech": TECH, "done": points >= cost, "points": points, "cost": cost}
