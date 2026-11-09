"""Cover point 0025.
"""
from __future__ import annotations

POINT = "cover_0025"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 25 % 2 == 0 else "high"}
