"""Reward 0069.
"""
from __future__ import annotations

REWARD = "reward_0069"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (69 % 30), "gold": 10 + (69 % 20)}
