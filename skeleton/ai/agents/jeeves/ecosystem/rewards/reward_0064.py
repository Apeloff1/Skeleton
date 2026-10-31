"""Reward 0064.
"""
from __future__ import annotations

REWARD = "reward_0064"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (64 % 30), "gold": 10 + (64 % 20)}
