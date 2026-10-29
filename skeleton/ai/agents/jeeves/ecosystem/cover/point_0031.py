"""Cover point 0031.
"""
from __future__ import annotations

POINT = "cover_0031"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 31 % 2 == 0 else "high"}
