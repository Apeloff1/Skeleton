"""Reward 0115.
"""
from __future__ import annotations

REWARD = "reward_0115"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (115 % 30), "gold": 10 + (115 % 20)}
