"""Reward 0036.
"""
from __future__ import annotations

REWARD = "reward_0036"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (36 % 30), "gold": 10 + (36 % 20)}
