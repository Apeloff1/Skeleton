"""Cover point 0039.
"""
from __future__ import annotations

POINT = "cover_0039"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 39 % 2 == 0 else "high"}
