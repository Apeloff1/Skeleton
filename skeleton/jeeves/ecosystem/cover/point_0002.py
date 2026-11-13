"""Cover point 0002.
"""
from __future__ import annotations

POINT = "cover_0002"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 2 % 2 == 0 else "high"}
