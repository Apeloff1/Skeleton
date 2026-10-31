"""Reward 0072.
"""
from __future__ import annotations

REWARD = "reward_0072"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (72 % 30), "gold": 10 + (72 % 20)}
