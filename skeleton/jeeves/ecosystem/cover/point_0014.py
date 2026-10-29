"""Cover point 0014.
"""
from __future__ import annotations

POINT = "cover_0014"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 14 % 2 == 0 else "high"}
