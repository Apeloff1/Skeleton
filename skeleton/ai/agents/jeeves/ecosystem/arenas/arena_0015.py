"""Arena 0015.
"""
from __future__ import annotations

ARENA = "arena_0015"

def queue(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "arena": ARENA, "player": player, "rating": 1000}
