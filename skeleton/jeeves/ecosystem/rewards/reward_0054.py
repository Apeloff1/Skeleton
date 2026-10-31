"""Reward 0054.
"""
from __future__ import annotations

REWARD = "reward_0054"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (54 % 30), "gold": 10 + (54 % 20)}
