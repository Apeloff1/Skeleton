"""Reward 0112.
"""
from __future__ import annotations

REWARD = "reward_0112"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (112 % 30), "gold": 10 + (112 % 20)}
