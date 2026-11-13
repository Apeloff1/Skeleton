"""Reward 0040.
"""
from __future__ import annotations

REWARD = "reward_0040"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (40 % 30), "gold": 10 + (40 % 20)}
