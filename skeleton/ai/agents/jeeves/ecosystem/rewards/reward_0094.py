"""Reward 0094.
"""
from __future__ import annotations

REWARD = "reward_0094"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (94 % 30), "gold": 10 + (94 % 20)}
