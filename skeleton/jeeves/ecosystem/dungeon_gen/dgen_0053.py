"""Dungeon gen 0053.
"""
from __future__ import annotations

DGEN = "dgen_0053"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (53 % 4)}
