"""Cover point 0010.
"""
from __future__ import annotations

POINT = "cover_0010"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 10 % 2 == 0 else "high"}
