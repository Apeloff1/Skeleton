"""Cover point 0019.
"""
from __future__ import annotations

POINT = "cover_0019"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 19 % 2 == 0 else "high"}
