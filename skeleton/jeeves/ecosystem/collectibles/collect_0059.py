"""Collectible 0059.
"""
from __future__ import annotations

COLLECT = "collect_0059"

def pickup(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "collect": COLLECT, "player": player, "points": 10 + (59 % 20)}
