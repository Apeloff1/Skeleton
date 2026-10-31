"""Cover point 0034.
"""
from __future__ import annotations

POINT = "cover_0034"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 34 % 2 == 0 else "high"}
