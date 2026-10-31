"""Reward 0008.
"""
from __future__ import annotations

REWARD = "reward_0008"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (8 % 30), "gold": 10 + (8 % 20)}
