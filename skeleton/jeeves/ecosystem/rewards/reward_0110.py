"""Reward 0110.
"""
from __future__ import annotations

REWARD = "reward_0110"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (110 % 30), "gold": 10 + (110 % 20)}
