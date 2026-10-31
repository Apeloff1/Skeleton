"""Cover point 0020.
"""
from __future__ import annotations

POINT = "cover_0020"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 20 % 2 == 0 else "high"}
