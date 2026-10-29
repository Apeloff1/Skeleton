"""Dungeon gen 0052.
"""
from __future__ import annotations

DGEN = "dgen_0052"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (52 % 4)}
