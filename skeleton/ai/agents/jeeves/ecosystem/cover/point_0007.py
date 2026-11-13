"""Cover point 0007.
"""
from __future__ import annotations

POINT = "cover_0007"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 7 % 2 == 0 else "high"}
