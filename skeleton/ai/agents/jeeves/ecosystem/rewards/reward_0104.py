"""Reward 0104.
"""
from __future__ import annotations

REWARD = "reward_0104"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (104 % 30), "gold": 10 + (104 % 20)}
