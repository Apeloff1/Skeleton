"""Reward 0028.
"""
from __future__ import annotations

REWARD = "reward_0028"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (28 % 30), "gold": 10 + (28 % 20)}
