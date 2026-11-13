"""Reward 0108.
"""
from __future__ import annotations

REWARD = "reward_0108"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (108 % 30), "gold": 10 + (108 % 20)}
