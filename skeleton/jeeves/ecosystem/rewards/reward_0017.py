"""Reward 0017.
"""
from __future__ import annotations

REWARD = "reward_0017"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (17 % 30), "gold": 10 + (17 % 20)}
