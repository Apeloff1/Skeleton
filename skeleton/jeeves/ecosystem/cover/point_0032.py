"""Cover point 0032.
"""
from __future__ import annotations

POINT = "cover_0032"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 32 % 2 == 0 else "high"}
