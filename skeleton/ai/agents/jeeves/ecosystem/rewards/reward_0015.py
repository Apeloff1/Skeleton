"""Reward 0015.
"""
from __future__ import annotations

REWARD = "reward_0015"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (15 % 30), "gold": 10 + (15 % 20)}
