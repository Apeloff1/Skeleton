"""Cover point 0009.
"""
from __future__ import annotations

POINT = "cover_0009"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 9 % 2 == 0 else "high"}
