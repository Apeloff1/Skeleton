"""Reward 0002.
"""
from __future__ import annotations

REWARD = "reward_0002"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (2 % 30), "gold": 10 + (2 % 20)}
