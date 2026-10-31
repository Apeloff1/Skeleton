"""Reward 0007.
"""
from __future__ import annotations

REWARD = "reward_0007"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (7 % 30), "gold": 10 + (7 % 20)}
