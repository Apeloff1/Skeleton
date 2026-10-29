"""Dungeon 0014.
"""
from __future__ import annotations

DUNGEON = "dungeon_0014"

def enter(party: list[str]) -> dict:
    if not party:
        return {"ok": False, "reason": "empty_party"}
    return {"ok": True, "dungeon": DUNGEON, "party": party[:4], "floors": 3 + (14 % 5)}
