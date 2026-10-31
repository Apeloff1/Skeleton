"""Cover point 0016.
"""
from __future__ import annotations

POINT = "cover_0016"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 16 % 2 == 0 else "high"}
