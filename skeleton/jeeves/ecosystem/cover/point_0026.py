"""Cover point 0026.
"""
from __future__ import annotations

POINT = "cover_0026"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 26 % 2 == 0 else "high"}
