"""Collectible 0048.
"""
from __future__ import annotations

COLLECT = "collect_0048"

def pickup(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "collect": COLLECT, "player": player, "points": 10 + (48 % 20)}
