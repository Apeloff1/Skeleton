"""Reward 0013.
"""
from __future__ import annotations

REWARD = "reward_0013"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (13 % 30), "gold": 10 + (13 % 20)}
