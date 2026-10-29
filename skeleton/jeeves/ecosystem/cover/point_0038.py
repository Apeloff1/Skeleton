"""Cover point 0038.
"""
from __future__ import annotations

POINT = "cover_0038"

def available(occupied: bool) -> dict:
    return {"ok": True, "point": POINT, "free": not occupied, "height": "low" if 38 % 2 == 0 else "high"}
