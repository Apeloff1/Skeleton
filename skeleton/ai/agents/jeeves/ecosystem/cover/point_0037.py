"""Cover point 0037.
"""
from __future__ import annotations

POINT = "cover_0037"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 37 % 2 == 0 else "high"}
