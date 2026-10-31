"""Reward 0059.
"""
from __future__ import annotations

REWARD = "reward_0059"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (59 % 30), "gold": 10 + (59 % 20)}
