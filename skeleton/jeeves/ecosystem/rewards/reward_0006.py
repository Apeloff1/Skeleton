"""Reward 0006.
"""
from __future__ import annotations

REWARD = "reward_0006"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (6 % 30), "gold": 10 + (6 % 20)}
