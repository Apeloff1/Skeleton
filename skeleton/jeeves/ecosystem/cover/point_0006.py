"""Cover point 0006.
"""
from __future__ import annotations

POINT = "cover_0006"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 6 % 2 == 0 else "high"}
