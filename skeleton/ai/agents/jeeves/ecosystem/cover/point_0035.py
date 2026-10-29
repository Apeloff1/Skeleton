"""Cover point 0035.
"""
from __future__ import annotations

POINT = "cover_0035"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 35 % 2 == 0 else "high"}
