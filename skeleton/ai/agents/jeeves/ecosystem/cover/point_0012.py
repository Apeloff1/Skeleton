"""Cover point 0012.
"""
from __future__ import annotations

POINT = "cover_0012"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 12 % 2 == 0 else "high"}
