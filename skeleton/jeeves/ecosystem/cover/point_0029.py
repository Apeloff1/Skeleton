"""Cover point 0029.
"""
from __future__ import annotations

POINT = "cover_0029"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 29 % 2 == 0 else "high"}
