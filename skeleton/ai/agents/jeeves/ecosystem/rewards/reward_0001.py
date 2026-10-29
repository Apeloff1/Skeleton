"""Reward 0001.
"""
from __future__ import annotations

REWARD = "reward_0001"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (1 % 30), "gold": 10 + (1 % 20)}
