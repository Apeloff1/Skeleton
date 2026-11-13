"""Reward 0095.
"""
from __future__ import annotations

REWARD = "reward_0095"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (95 % 30), "gold": 10 + (95 % 20)}
