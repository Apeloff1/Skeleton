"""Collectible 0076.
"""
from __future__ import annotations

COLLECT = "collect_0076"

def pickup(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "collect": COLLECT, "player": player, "points": 10 + (76 % 20)}
