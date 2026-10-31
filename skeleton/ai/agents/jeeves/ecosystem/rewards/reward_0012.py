"""Reward 0012.
"""
from __future__ import annotations

REWARD = "reward_0012"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (12 % 30), "gold": 10 + (12 % 20)}
