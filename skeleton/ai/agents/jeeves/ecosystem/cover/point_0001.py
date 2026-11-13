"""Cover point 0001.
"""
from __future__ import annotations

POINT = "cover_0001"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 1 % 2 == 0 else "high"}
