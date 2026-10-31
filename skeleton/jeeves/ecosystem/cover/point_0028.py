"""Cover point 0028.
"""
from __future__ import annotations

POINT = "cover_0028"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 28 % 2 == 0 else "high"}
