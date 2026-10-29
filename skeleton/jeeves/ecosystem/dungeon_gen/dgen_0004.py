"""Dungeon gen 0004.
"""
from __future__ import annotations

DGEN = "dgen_0004"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (4 % 4)}
