"""Nav mesh 0019.
"""
from __future__ import annotations

MESH = "nav_0019"

def bake(rooms: int) -> dict:
    if rooms < 1:
        return {"ok": False, "reason": "no_rooms"}
    return {"ok": True, "mesh": MESH, "polys": rooms * 4, "links": rooms - 1}
