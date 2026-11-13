"""Arena 0014.
"""
from __future__ import annotations

ARENA = "arena_0014"

def queue(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "arena": ARENA, "player": player, "rating": 1000}
