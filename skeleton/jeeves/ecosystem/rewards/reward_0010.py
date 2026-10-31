"""Reward 0010.
"""
from __future__ import annotations

REWARD = "reward_0010"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (10 % 30), "gold": 10 + (10 % 20)}
