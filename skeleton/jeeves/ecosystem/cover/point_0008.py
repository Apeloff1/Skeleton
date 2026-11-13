"""Cover point 0008.
"""
from __future__ import annotations

POINT = "cover_0008"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 8 % 2 == 0 else "high"}
