"""Cover point 0023.
"""
from __future__ import annotations

POINT = "cover_0023"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 23 % 2 == 0 else "high"}
