"""Reward 0025.
"""
from __future__ import annotations

REWARD = "reward_0025"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (25 % 30), "gold": 10 + (25 % 20)}
