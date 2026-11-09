"""Cover point 0027.
"""
from __future__ import annotations

POINT = "cover_0027"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 27 % 2 == 0 else "high"}
