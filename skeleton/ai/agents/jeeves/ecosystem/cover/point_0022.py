"""Cover point 0022.
"""
from __future__ import annotations

POINT = "cover_0022"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 22 % 2 == 0 else "high"}
