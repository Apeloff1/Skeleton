"""Reward 0102.
"""
from __future__ import annotations

REWARD = "reward_0102"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (102 % 30), "gold": 10 + (102 % 20)}
