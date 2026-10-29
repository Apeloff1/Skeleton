"""Dungeon gen 0056.
"""
from __future__ import annotations

DGEN = "dgen_0056"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (56 % 4)}
