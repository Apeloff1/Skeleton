"""Cover point 0013.
"""
from __future__ import annotations

POINT = "cover_0013"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 13 % 2 == 0 else "high"}
