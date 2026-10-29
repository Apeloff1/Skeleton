"""Collectible 0065.
"""
from __future__ import annotations

COLLECT = "collect_0065"

def pickup(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "collect": COLLECT, "player": player, "points": 10 + (65 % 20)}
