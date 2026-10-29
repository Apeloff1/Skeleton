"""Dungeon gen 0069.
"""
from __future__ import annotations

DGEN = "dgen_0069"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (69 % 4)}
