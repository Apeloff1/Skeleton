"""Cover point 0021.
"""
from __future__ import annotations

POINT = "cover_0021"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 21 % 2 == 0 else "high"}
