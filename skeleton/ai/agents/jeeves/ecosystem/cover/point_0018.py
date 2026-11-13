"""Cover point 0018.
"""
from __future__ import annotations

POINT = "cover_0018"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 18 % 2 == 0 else "high"}
