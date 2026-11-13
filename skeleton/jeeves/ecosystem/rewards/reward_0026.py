"""Reward 0026.
"""
from __future__ import annotations

REWARD = "reward_0026"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (26 % 30), "gold": 10 + (26 % 20)}
