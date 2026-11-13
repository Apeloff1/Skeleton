"""Cover point 0015.
"""
from __future__ import annotations

POINT = "cover_0015"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 15 % 2 == 0 else "high"}
