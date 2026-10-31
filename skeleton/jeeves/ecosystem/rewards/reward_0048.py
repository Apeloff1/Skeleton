"""Reward 0048.
"""
from __future__ import annotations

REWARD = "reward_0048"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (48 % 30), "gold": 10 + (48 % 20)}
