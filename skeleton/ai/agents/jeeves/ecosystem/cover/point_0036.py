"""Cover point 0036.
"""
from __future__ import annotations

POINT = "cover_0036"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 36 % 2 == 0 else "high"}
