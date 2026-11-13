"""Reward 0004.
"""
from __future__ import annotations

REWARD = "reward_0004"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (4 % 30), "gold": 10 + (4 % 20)}
