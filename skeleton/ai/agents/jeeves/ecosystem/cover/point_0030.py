"""Cover point 0030.
"""
from __future__ import annotations

POINT = "cover_0030"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 30 % 2 == 0 else "high"}
