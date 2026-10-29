"""Cover point 0004.
"""
from __future__ import annotations

POINT = "cover_0004"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 4 % 2 == 0 else "high"}
