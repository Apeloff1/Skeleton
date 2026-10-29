"""Dungeon 0025.
"""
from __future__ import annotations

DUNGEON = "dungeon_0025"

def enter(party: list[str]) -> dict:
    if not party:
        return {"ok": False, "reason": "empty_party"}
    return {"ok": True, "dungeon": DUNGEON, "party": party[:4], "floors": 3 + (25 % 5)}
