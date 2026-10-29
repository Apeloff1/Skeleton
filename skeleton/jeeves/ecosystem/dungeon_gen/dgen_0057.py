"""Dungeon gen 0057.
"""
from __future__ import annotations

DGEN = "dgen_0057"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (57 % 4)}
