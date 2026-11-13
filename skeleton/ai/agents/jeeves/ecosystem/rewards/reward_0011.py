"""Reward 0011.
"""
from __future__ import annotations

REWARD = "reward_0011"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (11 % 30), "gold": 10 + (11 % 20)}
