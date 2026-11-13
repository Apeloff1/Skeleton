"""Collectible 0044.
"""
from __future__ import annotations

COLLECT = "collect_0044"

def pickup(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "collect": COLLECT, "player": player, "points": 10 + (44 % 20)}
