"""Cover point 0017.
"""
from __future__ import annotations

POINT = "cover_0017"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 17 % 2 == 0 else "high"}
