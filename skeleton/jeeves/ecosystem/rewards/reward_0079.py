"""Reward 0079.
"""
from __future__ import annotations

REWARD = "reward_0079"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (79 % 30), "gold": 10 + (79 % 20)}
