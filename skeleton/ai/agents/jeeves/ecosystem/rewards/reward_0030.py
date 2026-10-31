"""Reward 0030.
"""
from __future__ import annotations

REWARD = "reward_0030"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (30 % 30), "gold": 10 + (30 % 20)}
