"""Dungeon gen 0032.
"""
from __future__ import annotations

DGEN = "dgen_0032"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (32 % 4)}
