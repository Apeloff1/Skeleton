"""Dungeon gen 0031.
"""
from __future__ import annotations

DGEN = "dgen_0031"

def layout(floors: int = 3) -> dict:
    floors = max(1, min(10, floors))
    return {"ok": True, "dgen": DGEN, "floors": floors, "rooms_per": 4 + (31 % 4)}
