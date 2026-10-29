"""Cover point 0011.
"""
from __future__ import annotations

POINT = "cover_0011"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 11 % 2 == 0 else "high"}
