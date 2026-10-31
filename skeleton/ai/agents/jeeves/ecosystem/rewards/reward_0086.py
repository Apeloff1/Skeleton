"""Reward 0086.
"""
from __future__ import annotations

REWARD = "reward_0086"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (86 % 30), "gold": 10 + (86 % 20)}
