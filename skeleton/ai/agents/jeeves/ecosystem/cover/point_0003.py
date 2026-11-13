"""Cover point 0003.
"""
from __future__ import annotations

POINT = "cover_0003"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 3 % 2 == 0 else "high"}
