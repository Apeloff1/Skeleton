"""Cover point 0024.
"""
from __future__ import annotations

POINT = "cover_0024"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 24 % 2 == 0 else "high"}
