"""Cover point 0033.
"""
from __future__ import annotations

POINT = "cover_0033"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 33 % 2 == 0 else "high"}
