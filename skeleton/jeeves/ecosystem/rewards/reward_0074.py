"""Reward 0074.
"""
from __future__ import annotations

REWARD = "reward_0074"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (74 % 30), "gold": 10 + (74 % 20)}
