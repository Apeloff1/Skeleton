"""Reward 0056.
"""
from __future__ import annotations

REWARD = "reward_0056"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (56 % 30), "gold": 10 + (56 % 20)}
