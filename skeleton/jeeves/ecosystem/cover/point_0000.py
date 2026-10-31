"""Cover point 0000.
"""
from __future__ import annotations

POINT = "cover_0000"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 0 % 2 == 0 else "high"}
